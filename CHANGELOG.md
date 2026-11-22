# Historia de versiones

## 0.2.0 — sin publicar

Cierra tres huecos de la 0.1.0 señalados en una auditoría del repositorio público.

- **Procedencia dentro del sello.** Cada corrida asienta `fecha_utc`, `version_modec_ce`,
  `commit` y `arbol_limpio` en el registro PLAN, un `instante_utc` por llamada y la fecha de
  cierre en el resumen (`modec_ce/procedencia.py`). Antes el sello ataba contenido y orden,
  pero no el momento ni la versión del código: la única fecha estaba en el nombre de la
  carpeta, fuera de la cadena. Si no hay repositorio git, `commit` queda en `null` y se
  declara AUSENTE, sin rellenarlo (P2).
- **Modo estricto de autenticidad.** Al verificar con clave, se exige que todo registro traiga
  el `key_id` esperado y un HMAC válido. Antes la firma solo se comprobaba en los registros
  que la traían: como `key_id` va dentro del cuerpo digestado, quien reescribiera la cadena
  podía quitar `key_id` y `hmac` de todos los registros, recalcular los digest y pasar la
  verificación limpia. Aplica a `modec_ce.nucleo.CadenaMinima` y a
  `herramientas/verificar_independiente.py`, que ahora acepta `--hmac-hex` y `--key-id`.
- **El verificador independiente reporta en vez de romperse.** Una LLAMADA malformada se
  informa como fallo; antes propagaba una excepción, y un tercero veía una traza en lugar de
  un informe.
- `verificar_independiente.py` declara en su salida la fecha, versión y commit del sello, y
  añade un límite explícito cuando la bitácora no los trae (es el caso de la bitácora 0.1.0
  publicada).
- `cargar_tarifa` acepta tarifas sin `cache_write`: antes lanzaba KeyError en vez de cobrar la
  escritura al precio de fallo, que es lo que `Tarifa.costo` ya sabía hacer.
- Límite declarado que esto NO resuelve: la fecha la pone el equipo que ejecuta. Convertirla en
  fecha verificable por un tercero requiere un ancla externa (sello de tiempo RFC 3161 sobre el
  digest del último registro).

### El informe publicado ya no se contradice con el repositorio

- `modec_ce informe` toma también las bitácoras versionadas en `evidencia/`, no solo las locales
  de `resultados/`. La página de GitHub Pages decía «Sin pilotos ejecutados» aunque el repositorio
  trae una bitácora verificable; ahora cita cada piloto con la ruta de su evidencia y la orden
  exacta para comprobarlo. Cuando no hay ninguna bitácora a la vista lo dice sin afirmar que no se
  ejecutaron pilotos, y enlaza a `evidencia/`.
- Cabecera del informe con autor, versión, licencia y enlaces al código, a las bitácoras y a los
  límites declarados: antes la página no permitía saber de quién era ni bajo qué licencia.

### Citación, lint y tipado

- `CITATION.cff`, con una prueba que falla si su versión se desfasa de `modec_ce.__version__` y
  otra que impide que se filtre un correo personal (el contacto va por el reporte privado de
  GitHub). Sin DOI hasta que exista el archivo en Zenodo; sin `date-released` hasta publicar 0.2.0.
- Trabajo `calidad` en el CI con ruff y mypy fijados a versión. Se eligieron reglas que encuentran
  defectos (`E`, `F`, `B`) y no las que reformatean; `line-length` recoge el ancho ya usado.
- Al habilitarlos salieron cuatro cosas de fondo, arregladas sin silenciar la regla:
  `uso_evaluable` no comprobaba `usage is None` antes de indexarlo; `nucleo.PESD` quedaba tipado
  como `None`, lo que hacía inalcanzable todo el camino con núcleo propietario disponible;
  `medir_compresion` importaba sobre el propio nombre `original`, de modo que el camino de réplica
  integrada parecía inalcanzable; y en `servidor_local` el `zip` de comparación de prefijos ahora
  declara `strict=False` (se detiene en el más corto, a propósito) mientras el de `simulacion`
  declara `strict=True`, para que falle antes que publicar una fila atribuida a otra petición.

Suite de 38 a 50 pruebas.

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
