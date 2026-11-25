# Sonidos de los hooks

Sonidos que reproducen `notify-on-stop` y `notify-on-permission` ([`../../tooling/notify-on-stop.md`](../../tooling/notify-on-stop.md)). Aquí solo entra audio cuya licencia permite redistribuirlo en un repo público, y la licencia se verifica en la página del propio archivo.

## `neb-chime.wav`

Sonido por defecto, en todo SO.

| Campo | Valor |
|---|---|
| Original | «Alert/Notification Sound», archivo `alert.wav` |
| Autor | frosty ham |
| Fuente | <https://opengameart.org/content/alertnotification-sound> (publicado el 2025-12-31) |
| Licencia | CC0 1.0, dominio público: <https://creativecommons.org/publicdomain/zero/1.0/>. No exige atribución; esta ficha la deja por trazabilidad |
| Descarga | 2026-11-24, de <https://opengameart.org/sites/default/files/alert.wav> |
| sha256 del original | `d275225f0d68e14331fade06451e3ce3a0f6665219936553968300557ff82666` (197 184 bytes; PCM 16 bit, estéreo, 48 kHz, 1.027 s) |
| Transformación | Estéreo a mono (promedio de canales), sin cambio de volumen (pico 7 098, −13.3 dBFS) ni de duración |
| sha256 del versionado | `86c1219d8ba24c121707966623e5694919c8249ff84390535380531eaeba2a2f` (98 614 bytes; PCM 16 bit, mono, 48 kHz) |

Los presets `"chimes"` y `"chimes-loud"` no viven aquí: usan el `chimes.wav` de Windows de la máquina del dev y la versión fuerte se genera en local (`../lib/notify_sound.py`), porque ese audio no se puede redistribuir.
