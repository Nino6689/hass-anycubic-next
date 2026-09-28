# Compatibility specification — `anycubic_cloud` 3.0

Facts a 3.0 release must reproduce so that an update from 2.x is seamless: nobody reconfigures, no entity id changes, stored history is kept. Collected 2026-09-28 by the specification team from a live 2.9.x install (Kobra S1 + one ACE Pro) and from the published translations. **This document states required behaviour and data formats only.**

## 1. Identity

| Item | Value |
|---|---|
| Domain | `anycubic_cloud` (must never change — it keys the entity registry, device registry and stored data) |
| Config entry version | 1 (minor 1) |
| Config entry unique id — cloud setup | the Anycubic account's numeric **user id**, as a string |
| Config entry unique id — LAN-only setup | the printer's MAC, formatted `aa:bb:cc:dd:ee:ff` (Home Assistant's `format_mac`); if the printer gives no MAC, `lan-<host>` |
| Config entry unique id — DHCP discovery | the discovered MAC, same format |

### Config entry `data` (set at setup)

| Key | Type | Meaning |
|---|---|---|
| `user_token` | str | the Anycubic access token the user pasted (absent on LAN-only entries) |
| `user_auth_mode` | int | which kind of token it is (web, slicer, Android — see §7) |
| `user_device_id` | str or null | device id, only needed for Android tokens |
| `region` | str | Anycubic cloud region: `international` or `china`; absent (older and LAN-only entries) means `international` |
| `printer_ids` | list[int] | the printers this entry covers |
| `lan_host` | str | LAN-only entries only: the printer address given at setup (the connection itself reads `options.lan_host`) |

### Config entry `options`

| Key | Type | Meaning |
|---|---|---|
| `mqtt_connect_mode` | int | when to hold the cloud MQTT connection open (always / only while printing / never) |
| `lan_mode_enabled` | bool | talk to the printer directly over LAN Mode |
| `lan_host` | str | printer IP address for LAN Mode |
| `drying_preset_duration_1..4` | int | minutes, drying preset N |
| `drying_preset_temperature_1..4` | int | °C, drying preset N |
| `card_config` | object | saved settings of the dashboard card |
| `debug_mqtt_msg` | bool | log raw MQTT messages |
| `debug_api_calls` | bool | log HTTP API calls |
| `debug` | bool | deprecated; ignore if present |

### Setup and options steps (step ids and field keys)

**config**

| Step id | Fields | Menu options |
|---|---|---|
| `auth_mode_android` | `user_token`, `user_device_id` |  |
| `auth_mode_pick` |  | `auth_mode_web`, `auth_mode_slicer`, `auth_mode_android` |
| `auth_mode_slicer` | `user_token` |  |
| `auth_mode_web` | `user_token` |  |
| `cloud` | `user_token`, `user_device_id`, `region` |  |
| `confirm_discovery` |  |  |
| `connection` | `lan_mode_enabled`, `lan_host` |  |
| `local` | `lan_host` |  |
| `printer` | `printer_ids` |  |
| `reauth_or_choose_printer` |  | `reauth`, `printer`, `connection` |
| `user` |  | `cloud`, `local` |

**options**

| Step id | Fields | Menu options |
|---|---|---|
| `options_menu` |  | `mqtt`, `drying`, `card_config`, `debug`, `local` |
| `mqtt` | `mqtt_connect_mode` |  |
| `drying` | `drying_preset_duration_1`, `drying_preset_temperature_1`, `drying_preset_duration_2`, `drying_preset_temperature_2`, `drying_preset_duration_3`, `drying_preset_temperature_3`, `drying_preset_duration_4`, `drying_preset_temperature_4` |  |
| `card_config` | `card_config` |  |
| `debug` | `debug_mqtt_msg`, `debug_api_calls` |  |
| `local` | `lan_mode_enabled`, `lan_host` |  |

## 2. Devices

| Device | Identifier `(anycubic_cloud, …)` | Notes |
|---|---|---|
| Printer | `<user id>-<printer id>` | manufacturer `Anycubic`; model = printer model name; name = printer name; MAC connection when known |
| First ACE | `<user id>-<printer id>-ace0` | child of the printer (`via_device`); model from the ACE model id (`40001` → `ACE Pro`; unknown → `ACE`); name `<printer name> <model>` |
| Second ACE | `<user id>-<printer id>-ace1` | as above; name `<printer name> <model> 2` |

**LAN-only entries** have no account, so the user-id part is the literal text **`None`**: the printer device is `None-<printer id>` and the ACE devices `None-<printer id>-ace0` / `-ace1`. 3.0 must reproduce this exactly or LAN-only users' devices duplicate.

**Printer id on LAN-only entries**: the printer's LAN `deviceId`; if it is all digits and at most 15 characters long it is used as that integer, otherwise it is the first 6 bytes of `BLAKE2b(deviceId, digest_size=6)` read as a big-endian unsigned integer (48 bits; always above real cloud ids, safe for Home Assistant's JSON storage). Cloud entries use the cloud's numeric printer id.

## 3. Entities

**Unique id** of every entity: `<printer MAC, upper-case, hyphen-separated>-<key>`, e.g. `A4-E8-8D-80-54-C8-nozzle_temperature`. Entity ids were generated from the device name plus the entity name, so keeping the device names and entity translation names (and `has_entity_name: true`) keeps new installs' entity ids identical too.

Existence rules (**Type** column): `printer` — every printer; `fdm` — filament printers only; `lcd` — resin printers only; `ace1`/`ace2` — only once that ACE unit is reported (entities must be *kept until* the unit reports, never dropped at setup — 2.x bug #41); `dry1`/`dry2` — per drying preset that has both a duration and a temperature set; `global` — once per entry.

### 3.1 Observed on a live install (Kobra S1 + one ACE Pro)

| Key (unique-id suffix) | Platform | Name (en) | Device | Unit | Device class | State class | Category | Enabled by default | Enum states | Extra attributes |
|---|---|---|---|---|---|---|---|---|---|---|
| `axis_move_failed` | binary_sensor | Axis move refused | printer |  | problem |  |  | yes |  |  |
| `axis_moving` | binary_sensor | Axis moving | printer |  | moving |  |  | yes |  |  |
| `dry_status_is_drying` | binary_sensor | Drying Active | ACE 1 |  |  |  |  | yes |  | `dry_status_code` |
| `external_spool_loaded` | binary_sensor | External spool loaded | printer |  |  |  |  | no |  |  |
| `is_available` | binary_sensor | Is Available | printer |  |  |  |  | yes |  |  |
| `is_busy` | binary_sensor | Is Busy | printer |  |  |  |  | yes |  |  |
| `job_complete` | binary_sensor | Job Complete | printer |  |  |  |  | yes |  |  |
| `job_failed` | binary_sensor | Job Failed | printer |  |  |  |  | yes |  |  |
| `job_filament_insufficient` | binary_sensor | Filament insufficient for job | printer |  | problem |  |  | yes |  |  |
| `job_in_progress` | binary_sensor | Job In Progress | printer |  |  |  |  | yes |  |  |
| `job_is_paused` | binary_sensor | Job Paused | printer |  |  |  |  | yes |  |  |
| `mqtt_connection_active` | binary_sensor | MQTT Connection Active | printer |  |  |  | diagnostic | yes |  | `last_error`, `supports_mqtt_login` |
| `printer_online` | binary_sensor | Printer Online | printer |  |  |  |  | yes |  |  |
| `ace_refresh_spools` | button | Refresh ACE Spools | ACE 1 |  |  |  |  | yes |  |  |
| `ace_retract` | button | ACE retract filament | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_1_feed` | button | ACE slot 1 feed | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_1_reset_spool` | button | ACE slot 1 reset spool | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_2_feed` | button | ACE slot 2 feed | ACE 1 |  |  |  |  | no |  |  |
| `ace_slot_2_reset_spool` | button | ACE slot 2 reset spool | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_3_feed` | button | ACE slot 3 feed | ACE 1 |  |  |  |  | no |  |  |
| `ace_slot_3_reset_spool` | button | ACE slot 3 reset spool | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_4_feed` | button | ACE slot 4 feed | ACE 1 |  |  |  |  | no |  |  |
| `ace_slot_4_reset_spool` | button | ACE slot 4 reset spool | ACE 1 |  |  |  | config | yes |  |  |
| `axis_home_all` | button | Home all axes | printer |  |  |  |  | yes |  |  |
| `axis_home_xy` | button | Home X and Y | printer |  |  |  |  | yes |  |  |
| `axis_home_z` | button | Home Z axis | printer |  |  |  |  | yes |  |  |
| `axis_motors_off` | button | Release motors | printer |  |  |  |  | yes |  |  |
| `axis_move_x_minus` | button | Move X minus | printer |  |  |  |  | yes |  |  |
| `axis_move_x_plus` | button | Move X plus | printer |  |  |  |  | yes |  |  |
| `axis_move_y_minus` | button | Move Y minus | printer |  |  |  |  | yes |  |  |
| `axis_move_y_plus` | button | Move Y plus | printer |  |  |  |  | yes |  |  |
| `axis_move_z_minus` | button | Move Z minus | printer |  |  |  |  | yes |  |  |
| `axis_move_z_plus` | button | Move Z plus | printer |  |  |  |  | yes |  |  |
| `cancel_print` | button | Cancel Print | printer |  |  |  |  | yes |  |  |
| `drying_start` | button | Start drying | ACE 1 |  |  |  |  | yes |  |  |
| `drying_stop` | button | Drying Stop | ACE 1 |  |  |  |  | yes |  |  |
| `pause_print` | button | Pause Print | printer |  |  |  |  | yes |  |  |
| `refresh_mqtt_connection` | button | Refresh MQTT Connection | printer |  |  |  | diagnostic | yes |  |  |
| `request_axis_position` | button | Request head position | printer |  |  |  | diagnostic | no |  |  |
| `request_file_list_cloud` | button | Request File List (Cloud) | printer |  |  |  |  | yes |  |  |
| `request_file_list_local` | button | Request File List (Local) | printer |  |  |  |  | yes |  |  |
| `request_file_list_udisk` | button | Request File List (USB Disk) | printer |  |  |  |  | yes |  |  |
| `reset_nozzle_wear` | button | Reset nozzle wear | printer |  |  |  | config | no |  |  |
| `resume_print` | button | Resume Print | printer |  |  |  |  | yes |  |  |
| `camera` | camera | Camera | printer |  |  |  |  | yes |  |  |
| `cloud_camera` | camera | Cloud camera | printer |  |  |  |  | yes |  |  |
| `job_image_url` | image | Job Preview | printer |  |  |  |  | yes |  |  |
| `printer_light` | light | Printer Light | printer |  |  |  |  | yes |  |  |
| `ace_slot_1_spool_price` | number | ACE slot 1 spool price per kg | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_1_spool_weight` | number | ACE slot 1 spool weight | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_2_spool_price` | number | ACE slot 2 spool price per kg | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_2_spool_weight` | number | ACE slot 2 spool weight | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_3_spool_price` | number | ACE slot 3 spool price per kg | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_3_spool_weight` | number | ACE slot 3 spool weight | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_4_spool_price` | number | ACE slot 4 spool price per kg | ACE 1 |  |  |  | config | yes |  |  |
| `ace_slot_4_spool_weight` | number | ACE slot 4 spool weight | ACE 1 |  |  |  | config | yes |  |  |
| `drying_set_duration` | number | Drying duration | ACE 1 | MINUTES | DURATION |  | config | yes |  |  |
| `drying_set_temperature` | number | Drying temperature | ACE 1 | CELSIUS | TEMPERATURE |  | config | yes |  |  |
| `set_aux_fan_speed_pct` | number | Set auxiliary fan speed | printer | PERCENTAGE |  |  |  | yes |  |  |
| `set_box_fan_level` | number | Set box fan level | printer |  |  |  |  | yes |  |  |
| `set_fan_speed_pct` | number | Set fan speed | printer | PERCENTAGE |  |  |  | yes |  |  |
| `set_target_hotbed_temp` | number | Set bed temperature | printer | CELSIUS | TEMPERATURE |  |  | yes |  |  |
| `set_target_nozzle_temp` | number | Set nozzle temperature | printer | CELSIUS | TEMPERATURE |  |  | yes |  |  |
| `axis_step` | select | Axis step size | printer |  |  |  |  | yes |  |  |
| `set_speed_mode` | select | Print speed mode | printer |  |  |  |  | yes |  |  |
| `ace_current_temperature` | sensor | ACE Current Temperature | ACE 1 | CELSIUS |  |  |  | yes |  |  |
| `ace_loaded_slot` | sensor | ACE Loaded Slot | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_1` | sensor | ACE Slot 1 | ACE 1 |  |  |  |  | yes |  | `color`, `color_hex`, `colors_hex`, `consumables_percent`, `edit_status`, `is_multi_color`, `sku`, `slot`, `spool_loaded`, `status` |
| `ace_slot_1_filament_remaining` | sensor | ACE slot 1 filament remaining | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_1_filament_remaining_percent` | sensor | ACE slot 1 filament remaining percent | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_2` | sensor | ACE Slot 2 | ACE 1 |  |  |  |  | yes |  | `color`, `color_hex`, `colors_hex`, `consumables_percent`, `edit_status`, `is_multi_color`, `sku`, `slot`, `spool_loaded`, `status` |
| `ace_slot_2_filament_remaining` | sensor | ACE slot 2 filament remaining | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_2_filament_remaining_percent` | sensor | ACE slot 2 filament remaining percent | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_3` | sensor | ACE Slot 3 | ACE 1 |  |  |  |  | yes |  | `color`, `color_hex`, `colors_hex`, `consumables_percent`, `edit_status`, `is_multi_color`, `sku`, `slot`, `spool_loaded`, `status` |
| `ace_slot_3_filament_remaining` | sensor | ACE slot 3 filament remaining | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_3_filament_remaining_percent` | sensor | ACE slot 3 filament remaining percent | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_4` | sensor | ACE Slot 4 | ACE 1 |  |  |  |  | yes |  | `color`, `color_hex`, `colors_hex`, `consumables_percent`, `edit_status`, `is_multi_color`, `sku`, `slot`, `spool_loaded`, `status` |
| `ace_slot_4_filament_remaining` | sensor | ACE slot 4 filament remaining | ACE 1 |  |  |  |  | yes |  |  |
| `ace_slot_4_filament_remaining_percent` | sensor | ACE slot 4 filament remaining percent | ACE 1 |  |  |  |  | yes |  |  |
| `ace_spools` | sensor | ACE Spools | ACE 1 |  |  |  |  | yes |  | `box_info`, `spool_info` |
| `aux_fan_speed_pct` | sensor | Auxiliary Fan Speed | printer | PERCENTAGE |  |  |  | yes |  |  |
| `axis_position_x` | sensor | Head position X | printer | MILLIMETERS | DISTANCE |  |  | no |  |  |
| `axis_position_y` | sensor | Head position Y | printer | MILLIMETERS | DISTANCE |  |  | no |  |  |
| `axis_position_z` | sensor | Head position Z | printer | MILLIMETERS | DISTANCE |  |  | no |  |  |
| `box_fan_level` | sensor | ACE Box Fan Level | ACE 1 |  |  |  |  | yes |  |  |
| `curr_hotbed_temp` | sensor | Hotbed Temperature | printer | CELSIUS |  |  |  | yes |  |  |
| `curr_nozzle_temp` | sensor | Nozzle Temperature | printer | CELSIUS |  |  |  | yes |  |  |
| `current_status` | sensor | Current Status | printer |  |  |  |  | yes |  | `device_status_code`, `is_printing_code`, `job_download_progress`, `machine_type`, `material_type`, `model`, `peripherals`, `print_status_code`, `supported_functions`, `total_material_used`, `total_print_time_dhm`, `total_print_time_hrs` |
| `dry_status_remaining_time` | sensor | Drying Remaining Time | ACE 1 |  |  |  |  | yes |  |  |
| `dry_status_target_temperature` | sensor | Drying Target Temperature | ACE 1 | CELSIUS |  |  |  | yes |  |  |
| `dry_status_total_duration` | sensor | Drying Total Duration | ACE 1 |  |  |  |  | yes |  |  |
| `external_spool_material` | sensor | External spool material | printer |  |  |  |  | no |  |  |
| `fan_speed_pct` | sensor | Fan Speed % | printer |  |  |  |  | yes |  |  |
| `filament_cost_total` | sensor | Filament cost total | printer |  | MONETARY | TOTAL |  | yes |  | `by_material_g` |
| `file_list_cloud` | sensor | File List (Cloud) | printer | 'files' |  |  |  | yes |  |  |
| `file_list_local` | sensor | File List (Local) | printer | 'files' |  |  |  | yes |  |  |
| `file_list_udisk` | sensor | File List (USB Disk) | printer | 'files' |  |  |  | yes |  |  |
| `job_cost` | sensor | Job cost | printer |  | MONETARY |  |  | yes |  |  |
| `job_current_layer` | sensor | Job Current Layer | printer | UNIT_LAYERS |  |  |  | yes |  |  |
| `job_eta` | sensor | Job ETA | printer |  | TIMESTAMP |  |  | yes |  |  |
| `job_filament_required` | sensor | Job filament required | printer | GRAMS | WEIGHT |  |  | yes |  |  |
| `job_filament_runs_out_at` | sensor | Job filament runs out at | printer | PERCENTAGE |  |  |  | no |  |  |
| `job_filament_shortfall` | sensor | Job filament shortfall | printer | GRAMS | WEIGHT |  |  | yes |  |  |
| `job_filament_used` | sensor | Job Filament Used | printer | MILLIMETERS |  |  |  | yes |  |  |
| `job_name` | sensor | Job Name | printer |  |  |  |  | yes |  |  |
| `job_progress` | sensor | Job Progress % | printer | PERCENTAGE |  |  |  | yes |  |  |
| `job_speed_mode` | sensor | Job Speed Mode | printer |  |  |  |  | yes |  | `available_modes`, `print_speed_mode_code` |
| `job_state` | sensor | Job State | printer |  |  |  |  | yes |  |  |
| `job_time_elapsed` | sensor | Job Time Elapsed | printer | MINUTES |  |  |  | yes |  |  |
| `job_time_remaining` | sensor | Job Time Remaining | printer | MINUTES |  |  |  | yes |  |  |
| `job_total_layers` | sensor | Job Total Layers | printer | UNIT_LAYERS |  |  |  | yes |  |  |
| `job_z_thick` | sensor | Job Z Thickness | printer |  |  |  |  | yes |  |  |
| `last_error` | sensor | Last Error | printer |  |  |  |  | yes |  |  |
| `last_error_code` | sensor | Last Error Code | printer |  |  |  |  | yes |  |  |
| `last_job_cost` | sensor | Last job cost | printer |  | MONETARY |  |  | yes |  |  |
| `last_job_filament` | sensor | Last job filament | printer | GRAMS | WEIGHT |  |  | no |  |  |
| `material_used_total` | sensor | Total Material Used | printer | KILOGRAMS |  | TOTAL_INCREASING | diagnostic | yes |  |  |
| `nozzle_abrasive_filament` | sensor | Nozzle abrasive filament | printer | GRAMS | WEIGHT | TOTAL_INCREASING | diagnostic | yes |  |  |
| `nozzle_filament_total` | sensor | Nozzle filament total | printer | GRAMS | WEIGHT | TOTAL_INCREASING | diagnostic | no |  |  |
| `nozzle_wear_percent` | sensor | Nozzle wear | printer | PERCENTAGE |  |  | diagnostic | yes |  |  |
| `print_count_total` | sensor | Total Print Count | printer |  |  | TOTAL_INCREASING | diagnostic | yes |  |  |
| `print_speed_pct` | sensor | Print Speed % | printer |  |  |  |  | yes |  |  |
| `print_time_total_hrs` | sensor | Total Print Time | printer | HOURS |  | TOTAL_INCREASING | diagnostic | yes |  |  |
| `spool_inventory_count` | sensor | Spool inventory count | printer |  |  |  |  | no |  |  |
| `spool_inventory_remaining` | sensor | Spool inventory remaining | printer | GRAMS | WEIGHT |  |  | yes |  | `spools` |
| `target_hotbed_temp` | sensor | Target Hotbed Temperature | printer | CELSIUS |  |  |  | yes |  | `limit_max`, `limit_min` |
| `target_nozzle_temp` | sensor | Target Nozzle Temperature | printer | CELSIUS |  |  |  | yes |  | `limit_max`, `limit_min` |
| `ai_detection_enabled` | switch | AI failure detection | printer |  |  |  | config | yes |  |  |
| `manual_mqtt_connection_enabled` | switch | Manual MQTT Connection Enabled | printer |  |  |  | diagnostic | yes |  |  |
| `multi_color_box_runout_refill` | switch | ACE Run-out Refill | ACE 1 |  |  |  |  | yes |  |  |
| `fw_version` | update | Printer Firmware | printer |  | FIRMWARE |  | config | yes |  |  |
| `multi_color_box_fw_version` | update | ACE Firmware | ACE 1 |  | FIRMWARE |  | config | yes |  |  |

### 3.2 Defined but not present on that install (second ACE, resin printers, presets, feature-gated)

| Key | Platform | Name (en) | Type | Unit | Device class | State class | Category | Enabled by default |
|---|---|---|---|---|---|---|---|---|
| `secondary_ace_current_temperature` | sensor | Secondary ACE Current Temperature | ACE_SECONDARY | CELSIUS |  |  |  | yes |
| `secondary_ace_loaded_slot` | sensor | Secondary ACE Loaded Slot | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_ace_spools` | sensor | Secondary ACE Spools | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_dry_status_target_temperature` | sensor | Secondary Drying Target Temperature | ACE_SECONDARY | CELSIUS |  |  |  | yes |
| `secondary_dry_status_total_duration` | sensor | Secondary Drying Total Duration | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_dry_status_remaining_time` | sensor | Secondary Drying Remaining Time | ACE_SECONDARY |  |  |  |  | yes |
| `job_on_time` | sensor | Job On Time | LCD | SECONDS |  |  |  | yes |
| `job_off_time` | sensor | Job Off Time | LCD | SECONDS |  |  |  | yes |
| `job_bottom_time` | sensor | Job Bottom Time | LCD | SECONDS |  |  |  | yes |
| `job_model_height` | sensor | Job Model Height | LCD | MILLIMETERS |  |  |  | yes |
| `job_anti_alias_count` | sensor | Job Anti Alias | LCD |  |  |  |  | yes |
| `job_bottom_layers` | sensor | Job Bottom Layers | LCD | UNIT_LAYERS |  |  |  | yes |
| `job_z_up_height` | sensor | Job Z Up Height | LCD | MILLIMETERS |  |  |  | yes |
| `job_z_up_speed` | sensor | Job Z Up Speed | LCD |  |  |  |  | yes |
| `job_z_down_speed` | sensor | Job Z Down Speed | LCD |  |  |  |  | yes |
| `secondary_dry_status_is_drying` | binary_sensor | Secondary Drying Active | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_ace_retract` | button | Secondary ACE Retract | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_drying_start` | button | Secondary Drying Start | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_drying_stop` | button | Secondary Drying Stop | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_multi_color_box_runout_refill` | switch | Secondary ACE Run-out Refill | ACE_SECONDARY |  |  |  |  | yes |
| `secondary_multi_color_box_fw_version` | update | Secondary ACE Firmware | ACE_SECONDARY |  | FIRMWARE |  | CONFIG | yes |

Per-slot and per-preset families (slot N = 1–4, preset N = 1–4, prefix `secondary_` for the second ACE): `ace_slot_N`, `ace_slot_N_filament_remaining`, `ace_slot_N_filament_remaining_percent`, `ace_slot_N_reset_spool`, `ace_slot_N_feed`, `ace_slot_N_spool_weight`, `ace_slot_N_spool_price`, `drying_start_preset_N`; axis jog buttons `axis_move_<axis>_<direction>` — see 3.1 for the exact members observed.

## 4. Actions (services)

Every action takes `config_entry` (**required**) plus one of `device_id` or `printer_id` to pick the printer (BEHAVIOUR.md §4.1).

| Action | Fields (besides the printer selector) |
|---|---|
| `anycubic_cloud.multi_color_box_set_slot_pla` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_petg` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_abs` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_pacf` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_pc` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_asa` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_hips` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_pa` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_set_slot_pla_se` | `box_id`, `slot_number`*, `slot_color_red`*, `slot_color_green`*, `slot_color_blue`* |
| `anycubic_cloud.multi_color_box_filament_extrude` | `box_id`, `slot_number`*, `finished` |
| `anycubic_cloud.multi_color_box_filament_retract` | `box_id` |
| `anycubic_cloud.print_and_upload_save_in_cloud` | `slot_number`, `uploaded_gcode_file`* |
| `anycubic_cloud.print_and_upload_no_cloud_save` | `slot_number`, `uploaded_gcode_file`* |
| `anycubic_cloud.print_local_file` | `filename`* |
| `anycubic_cloud.delete_file_local` | `filename`* |
| `anycubic_cloud.delete_file_udisk` | `filename`* |
| `anycubic_cloud.delete_file_cloud` | `file_id`* |
| `anycubic_cloud.change_print_speed_mode` | `speed_mode`* |
| `anycubic_cloud.change_print_target_nozzle_temperature` | `temperature`* |
| `anycubic_cloud.change_print_target_hotbed_temperature` | `temperature`* |
| `anycubic_cloud.change_print_fan_speed` | `speed`* |
| `anycubic_cloud.change_print_aux_fan_speed` | `speed`* |
| `anycubic_cloud.change_print_box_fan_speed` | `speed`* |
| `anycubic_cloud.change_print_bottom_layers` | `layers`* |
| `anycubic_cloud.change_print_bottom_time` | `time`* |
| `anycubic_cloud.change_print_off_time` | `time`* |
| `anycubic_cloud.change_print_on_time` | `time`* |

`*` = required. Field types, selectors, ranges, preconditions and errors: BEHAVIOUR.md §4 (answers C2).

## 5. Events and repairs

| Kind | Id | When |
|---|---|---|
| Event | event type **`anycubic_cloud`**, data `{printer_id, printer_name, device_id, type: "print_cloud_start", event_data: {…the order's result…}}` (keys in BEHAVIOUR.md §4.8) | after a print is started from the cloud via an action |
| Repair | `token_expiring_<entry id>` (translation key `token_expiring`) | the pasted token expires within 14 days; removed once renewed |
| Repair / error | translation key `mqtt_connect_timeout` | the cloud MQTT connection could not be established |

## 6. Stored data (`.storage`) — must be read as-is by 3.0

### `anycubic_cloud.filament.<entry id>` (version 1) — filament ledger

```
{ printers: { "<printer id>": {
    slots: { "0".."3": { spool_weight_g: float, filament_used_g: float, spool_signature: str, spool_price_per_kg?: float } },
    last_job_id: int,
    totals: { material_totals: { "<material>": float grams }, last_job_grams: float, last_job_cost: float|null, cost_total: float },
    nozzle: { nozzle_total_g: float, nozzle_abrasive_g: float },
    axis_step: int, drying_settings?: { temperature?: float, duration?: float }, feeding_slot?: int } },
  spools: { "<material>|<#RRGGBB>|<sku>": { filament_used_g: float, spool_weight_g: float, spool_price_per_kg?: float } },
  jobs:   { "<job name>": [ float, ... ] } }
```

A spool's signature is `material|#RRGGBB|sku` (SKU may be empty). A reel taken out and put back — in any slot — is matched by signature and keeps its history. `jobs` holds per-job gram figures used by the run-out forecast.

### `anycubic_cloud.capabilities.<entry id>` (version 1)

```
{ printers: { "<printer id>": { light_types: [int] } } }
```

### `anycubic_cloud.<entry id>` (version 1) — cloud session

```
{ app_client_id, app_id, app_version, app_secret, auth_token, device_id|null, auth_access_token, auth_mode: int }
```
Secrets: never logged, never in diagnostics. A legacy un-suffixed `anycubic_cloud` store with the same shape may exist from older versions.

## 7. Open questions for the specification team

- ~~C1~~ — answered in §2.
- ~~C2~~ — answered in [`BEHAVIOUR.md`](BEHAVIOUR.md) §4 (every action's fields, selectors, ranges, preconditions, transports and errors).
- ~~C3~~ — answered in [`BEHAVIOUR.md`](BEHAVIOUR.md) §1–§3 (meaning, source, transport and format of every entity key).

