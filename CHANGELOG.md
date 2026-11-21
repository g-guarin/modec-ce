# Historia de versiones

## 0.1.0 — 2026-11-21

Primera versión publicable.

- Cuatro variantes: tres disposiciones (`ingenua_volatil`, `ingenua_rol`, `modec`), con la misma huella de contenido entre ellas, y `modec_compresion` (`modec` con el historial en Super-Tokens).
- Modelo de caché de prefijos limitado a las reglas R1–R3 que publica DeepSeek.
- Costo en `Decimal` con tarifas declaradas (`datos/precios.json`, leídas el 2026-11-20).
- Adaptadores para DeepSeek, Anthropic, OpenAI, OpenRouter y un servidor local (transformador en CPU con caché KV real).
- Piloto A/B con 3 corridas, nonce por corrida, orden de los brazos alternado, topes y fallo cerrado.
- Evidencia sellada: núcleo PESD 2.0.0 si está disponible; si no, una cadena mínima integrada. Cada resultado declara qué motor la selló.
- Métrica C.1: instrumento original de MODEC si está disponible; si no, una réplica integrada, cuya equivalencia con el original se comprueba con una prueba que solo se ejecuta si el paquete MODEC original está instalado.
- Piloto real con DeepSeek (la segunda de dos ejecuciones ese día; la primera no se publica): 48 llamadas, 65,3 % de ahorro de costo (sin mejora de latencia) y la bitácora sellada con la cadena mínima publicada en `evidencia/`.
- Las redirecciones HTTP ya no se siguen, para no reenviar la cabecera de autorización a otro destino.
- El piloto se detiene, sin hacer llamadas, si el contenido no es idéntico entre brazos.
- Documentación: la simulación se declara estimación (no cota), se explican los términos y se corrigen las cifras de corpus.
- `herramientas/verificar_independiente.py`: verifica una bitácora publicada sin el núcleo PESD.
