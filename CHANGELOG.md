# Historia de versiones

## 0.1.0 — 2026-11-21

Primera versión publicable.

- Cuatro disposiciones (`ingenua_volatil`, `ingenua_rol`, `modec`, `modec_compresion`), con la misma huella de contenido entre las tres primeras.
- Modelo de caché de prefijos limitado a las reglas R1–R3 que publica DeepSeek.
- Costo en `Decimal` con tarifas declaradas (`datos/precios.json`, leídas el 2026-11-20).
- Adaptadores para DeepSeek, Anthropic, OpenAI, OpenRouter y un servidor local (transformador en CPU con caché KV real).
- Piloto A/B con 3 corridas, nonce por corrida, orden de los brazos alternado, topes y fallo cerrado.
- Evidencia sellada: núcleo PESD 2.0.0 si está disponible; si no, una cadena mínima integrada. Cada resultado declara qué motor la selló.
- Métrica C.1: instrumento original de MODEC si está disponible; si no, una réplica integrada cuya equivalencia se comprueba con una prueba.
- Primer piloto real con DeepSeek: 48 llamadas, 65,3 % de ahorro medio de costo (sin mejora de latencia) y la bitácora sellada publicada en `evidencia/`.
- `herramientas/verificar_independiente.py`: verifica una bitácora publicada sin el núcleo PESD.
