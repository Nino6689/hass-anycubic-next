"""A fake Anycubic cloud behind anycubic-cloud-client's public API.

The integration is tested against the library's interface only: the HTTP
client, the MQTT link and the Agora session are replaced here, while the
library's own models (``PrinterDetail.from_data`` ...) and message parser
(``parse_cloud_message``) are used as they are, so the data shapes are real.
"""

from __future__ import annotations

from collections.abc import Callable
import datetime
from functools import cache
from typing import Any

from anycubic_cloud_client import (
    Account,
    AuthMode,
    CameraCredentials,
    CloudFile,
    CloudMessage,
    CloudSecrets,
    CredentialsRejectedError,
    Job,
    JobDetail,
    MqttError,
    PrinterDetail,
    PrinterSummary,
    PrintStartResult,
    Region,
    SignInResult,
    TokenState,
    parse_cloud_message,
    select_latest_job,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from . import cloud_payloads as cp


@cache
def fake_secrets() -> CloudSecrets:
    """Obviously fake credentials with a certificate made at test time."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fake")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return CloudSecrets(
        app_id="fake-app-id",
        app_secret="fake-app-secret",
        client_id_web="fake-web",
        client_id_app="fake-app",
        mqtt_ca_pem=cert_pem,
        mqtt_client_cert_pem=cert_pem,
        mqtt_client_key_pem=key_pem,
    )


class FakeCloud:
    """What the fake account holds and answers."""

    def __init__(self) -> None:
        self.user = cp.user_info()
        self.printers: dict[int, dict[str, Any]] = {cp.PRINTER_ID: cp.detail()}
        self.jobs: list[dict[str, Any]] = [cp.job()]
        self.job_details: dict[int, dict[str, Any]] = {cp.JOB_ID: cp.job_detail()}
        self.files: list[dict[str, Any]] = [cp.cloud_file()]
        self.check_errors: list[Exception] = []
        """Raised by the next ``check()`` calls, one each."""
        self.reject_stored = False
        """Refuse a client built with a stored session (PROTOCOL A §5.3)."""
        self.printer_errors: dict[int, Exception] = {}
        self.list_error: Exception | None = None
        self.order_error: Exception | None = None
        self.camera: dict[str, Any] | Exception = cp.camera_reply()
        self.exchanged_tokens: TokenState | None = None
        """Tokens the next check() derives (marks ``tokens_changed``)."""
        self.orders: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.clients: list[FakeClient] = []
        self.links: list[FakeLink] = []
        self.mqtt_error: MqttError | None = None
        self.mqtt_connects = False
        """Whether ``connect()`` succeeds at once (else it waits for a test)."""
        self.upload_result: PrintStartResult | Exception | None = None
        self.checks = 0
        self.printer_reads = 0

    # -- helpers for tests --------------------------------------------------

    @property
    def client(self) -> FakeClient:
        return self.clients[-1]

    @property
    def link(self) -> FakeLink:
        return self.links[-1]

    def order_names(self) -> list[str]:
        return [name for name, _, _ in self.orders]

    def feed(self, payload: dict[str, Any], *, key: str = cp.PRINTER_KEY) -> None:
        """A message from the broker, through the library's own parser."""
        message = parse_cloud_message(cp.topic(str(payload["type"]), key), payload)
        assert message is not None
        self.link.deliver(message)


class FakeClient:
    """Stands in for ``AnycubicCloudClient``."""

    def __init__(
        self,
        cloud: FakeCloud,
        *,
        token: str,
        auth_mode: AuthMode,
        region: Region,
        device_id: str | None,
        store: Any,
    ) -> None:
        self.cloud = cloud
        self.token = token
        self.auth_mode = auth_mode
        self.region = region
        self.device_id = device_id
        self.store = dict(store) if store else None
        self.account: Account | None = None
        self.tokens_changed = False
        self.secrets = fake_secrets()
        self.user_token: str | None = token
        if self.store is not None and self.store.get("auth_token"):
            self.user_token = self.store["auth_token"]
        cloud.clients.append(self)

    @classmethod
    def factory(cls, cloud: FakeCloud) -> Any:
        class _Factory:
            @staticmethod
            def from_entry(
                session: Any,
                secrets: Any,
                *,
                token: str,
                auth_mode: Any,
                region: Any = None,
                device_id: str | None = None,
                store: Any = None,
                debug_api_calls: bool = False,
            ) -> FakeClient:
                return cls(
                    cloud,
                    token=token,
                    auth_mode=AuthMode.resolve(auth_mode),
                    region=Region.resolve(region),
                    device_id=device_id,
                    store=store,
                )

        return _Factory

    # -- tokens -------------------------------------------------------------

    @property
    def supports_mqtt_login(self) -> bool:
        return self.auth_mode.supports_mqtt and bool(self.user_token)

    @property
    def token_state(self) -> TokenState:
        return TokenState(
            auth_token=self.user_token,
            auth_access_token=self.token if self.auth_mode is AuthMode.SLICER else None,
            device_id=self.device_id,
            auth_mode=self.auth_mode,
        )

    def export_token_store(self) -> dict[str, Any]:
        return self.token_state.to_store()

    def mark_tokens_saved(self) -> None:
        self.tokens_changed = False

    async def check(self) -> Account:
        self.cloud.checks += 1
        if self.cloud.check_errors:
            raise self.cloud.check_errors.pop(0)
        if self.cloud.reject_stored and self.store is not None:
            raise CredentialsRejectedError("stored session refused")
        if (tokens := self.cloud.exchanged_tokens) is not None:
            self.cloud.exchanged_tokens = None
            self.user_token = tokens.auth_token
            self.tokens_changed = True
        self.account = Account.from_data(self.cloud.user)
        return self.account

    # -- reads --------------------------------------------------------------

    async def get_printers(self) -> list[PrinterSummary]:
        if self.cloud.list_error is not None:
            raise self.cloud.list_error
        return [PrinterSummary.from_data(p) for p in self.cloud.printers.values()]

    async def get_printer(self, printer_id: int) -> PrinterDetail:
        self.cloud.printer_reads += 1
        if (error := self.cloud.printer_errors.get(printer_id)) is not None:
            raise error
        return PrinterDetail.from_data(self.cloud.printers[printer_id])

    async def get_latest_jobs(self, printer_ids: list[int]) -> dict[int, Job | None]:
        jobs = [Job.from_data(j) for j in self.cloud.jobs]
        return {pid: select_latest_job(jobs, pid) for pid in printer_ids}

    async def get_job_detail(self, job_id: int) -> JobDetail:
        return JobDetail.from_data(self.cloud.job_details.get(job_id, {}))

    async def list_cloud_files(self) -> list[CloudFile]:
        return [CloudFile.from_data(f) for f in self.cloud.files]

    async def open_camera(self, printer_id: int) -> CameraCredentials:
        self.cloud.orders.append(("open_camera", (printer_id,), {}))
        reply = self.cloud.camera
        if isinstance(reply, Exception):
            raise reply
        credentials = CameraCredentials.from_data(reply)
        assert credentials is not None
        return credentials

    # -- everything else is an order, recorded ------------------------------

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("_"):
            raise AttributeError(name)

        async def order(*args: Any, **kwargs: Any) -> Any:
            self.cloud.orders.append((name, args, kwargs))
            if self.cloud.order_error is not None:
                raise self.cloud.order_error
            if name == "upload_and_print":
                result = self.cloud.upload_result
                if isinstance(result, Exception):
                    raise result
                return result
            if name == "update_printer_firmware":
                return "2.8.0.0"
            if name == "delete_cloud_files":
                return None
            return "msgid"

        return order


class FakeLink:
    """Stands in for ``CloudMqttClient``."""

    def __init__(self, cloud: FakeCloud, client: Any, debug_messages: bool) -> None:
        self.cloud = cloud
        self.client = client
        self.debug_messages = debug_messages
        self.is_running = False
        self.is_connected = False
        self.subscribed: dict[str, int] = {}
        self._messages: list[Callable[[CloudMessage], None]] = []
        self._connection: list[Callable[[bool, MqttError | None], None]] = []
        self.disconnects = 0
        self.connects = 0
        cloud.links.append(self)

    @classmethod
    def factory(cls, cloud: FakeCloud) -> Callable[..., FakeLink]:
        def build(client: Any, *, debug_messages: bool = False) -> FakeLink:
            return cls(cloud, client, debug_messages)

        return build

    def add_message_listener(self, callback: Any) -> Callable[[], None]:
        self._messages.append(callback)
        return lambda: None

    def add_connection_listener(self, callback: Any) -> Callable[[], None]:
        self._connection.append(callback)
        return lambda: None

    def subscribe_printer(self, key: str, machine_type: int) -> None:
        self.subscribed[key] = machine_type

    async def connect(self) -> None:
        self.connects += 1
        if self.cloud.mqtt_error is not None:
            raise self.cloud.mqtt_error
        self.is_running = True
        self.is_connected = True
        for callback in list(self._connection):
            callback(True, None)

    async def disconnect(self) -> None:
        self.disconnects += 1
        self.is_running = False
        self.is_connected = False

    def drop(self, error: MqttError | None = None) -> None:
        """The link drops (or gives up with ``error``)."""
        self.is_connected = False
        if error is not None:
            self.is_running = False
        for callback in list(self._connection):
            callback(False, error)

    def deliver(self, message: CloudMessage) -> None:
        for callback in list(self._messages):
            callback(message)


def sign_in_result(cloud: FakeCloud, token: str, mode: AuthMode) -> SignInResult:
    client = FakeClient(
        cloud,
        token=token,
        auth_mode=mode,
        region=Region.INTERNATIONAL,
        device_id=None,
        store=None,
    )
    account = Account.from_data(cloud.user)
    client.account = account
    return SignInResult(
        auth_mode=mode,
        account=account,
        tokens=TokenState(
            auth_token="derived-user-token",
            auth_access_token=token,
            auth_mode=mode,
        ),
        client=client,  # type: ignore[arg-type]
    )
