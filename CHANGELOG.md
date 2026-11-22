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

### Documentación puesta al día con el ancla

- `docs/caso-de-uso.md` enseñaba una salida del verificador con «SIN ANCLA EXTERNA» cuando esa
  bitácora ya tenía ancla: el documento mostraba algo que el programa no produce. Corregido, y con
  una prueba que compara el bloque de ejemplo, campo por campo, con lo que la herramienta imprime.
- `README.en.md` no mencionaba el ancla. Ahora la describe, da el comando de verificación y declara
  la diferencia entre las dos bitácoras, igual que el español.

### Ancla temporal RFC 3161 sobre la bitácora del 2026-11-22

- Publicada en `sello/piloto_deepseek_20261122_135846_5c1d7c/`: solicitud, respuesta firmada por
  FreeTSA, los dos certificados de la autoridad y el registro completo de la operación. Instante
  acreditado: 22 de noviembre de 2026, 22:17:24 GMT. Verificada en un equipo distinto del que la
  produjo y con otra versión de OpenSSL: `Verification: OK`, estado `Granted`, y el valor sellado
  es el digest final de esa cadena, exacto.
- Con ella, reescribir la bitácora entera deja de ser indetectable, que era el límite más grande
  que quedaba declarado.
- `verificar_independiente.py` detecta el ancla y distingue tres casos: ausente, presente y
  correspondiente a esa cadena, o presente y de otra cadena. La comprobación no necesita
  dependencias: el digest final en bruto tiene que estar dentro de la solicitud y de la respuesta.
  Lo que NO comprueba es la firma de la autoridad —exige ASN.1— y lo declara en su salida en vez
  de darlo por hecho. Tres pruebas lo cubren, incluida la de colocar el ancla de otra cadena.
- Los certificados de la autoridad se publican junto al sello: si FreeTSA dejara de estar
  disponible, harían falta para verificar.

### La ficha de latencia dejaba de ser honesta al resumir

- El informe titulaba la latencia con «reducción mínima por corrida», es decir, con el peor dato de
  las tres. Elegir el dato desfavorable es el mismo error que elegir el favorable: ninguno de los
  dos es la medición, y además contradecía al README, que ya declara que no hay efecto medible.
- Ahora muestra el rango completo y cuántas corridas salieron mejor (`-7,7 % a 3,1 % · dispersión,
  no efecto · mejor en 2 de 3 corridas`). Dos pruebas lo sostienen: una comprueba `_rango_latencia`
  y otra que la página no vuelva a titular con un solo extremo.

### Caso de uso: cómo se ve una entrega hecha con esto

- `docs/caso-de-uso.md`: un ejemplo trabajado de una entrega a un cliente, construido con la
  bitácora real del piloto del 2026-11-22. Contrasta una afirmación de ahorro no auditable con la
  misma cifra respaldada por evidencia sellada, enumera qué comprueba el cliente en dos minutos y
  qué sigue sin estar probado, y explica por qué debe exigir que se mida su propia carga.
- Dos pruebas lo sostienen: una comprueba que cada cifra del documento sale de `resumen.json` de la
  bitácora publicada, y otra que el documento declara que el escenario es ilustrativo. Un informe
  de ejemplo que no se declara como tal es un registro fabricado, y este repositorio no publica eso.
- Enlazado desde ambos README.

### Posicionamiento: qué resuelve esto que la documentación del proveedor no resuelve

El repositorio exponía bien QUÉ mide y mal PARA QUÉ sirve. Montaba un aparato de evidencia sin
declarar nunca contra qué protege, lo que invita a leerlo como sobre-ingeniería.

- **Modelo de amenaza declarado** en SECURITY.md, con una tabla de qué manipulación detecta la
  cadena y cuál no. La fila que importa es la que dice que NO: elegir una carga o una tarifa
  favorables no lo detecta nada, y eso no se arregla con criptografía.
- **Para quién es**, en ambos README: quien debe sostener una cifra de costo ante otro —consultoría,
  compras, auditoría, publicación—, no quien solo quiere una factura menor. La técnica de disposición
  es práctica recomendada por los proveedores y no se propone como novedad; lo que se propone es que
  la medición quede sellada y la pueda comprobar un tercero.
- **`sensibilidad_salida()`** y tabla en los dos README: con el acierto de caché MEDIDO en el piloto
  y sin cambiar nada más, alargar la salida lleva el ahorro del 65 % al 12 %. La disposición abarata
  la entrada y no toca la salida. Una prueba comprueba que la tabla coincide con el código.
  Esa dependencia es el argumento, no una concesión: si el ahorro depende tanto de la forma de la
  carga, un porcentaje ajeno no sirve para decidir y hay que medir el propio.
- **Procedencia de los patrones**: se declara que el sellado encadenado (P1) y el centinela de
  presencia (P2) provienen del marco de patrones estructurales PESD del autor, señalando el archivo
  que implementa cada uno. Se mencionan porque son inspeccionables y están cubiertos por pruebas en
  este mismo repositorio, no como referencia a un componente que no se pueda examinar.
- Metadatos de descubrimiento: resumen y palabras clave de CITATION.cff reescritos hacia
  verificabilidad y auditoría; `description`, `author` y etiquetas Open Graph en el informe HTML, y
  un párrafo de tesis en su cabecera.

### Segundo piloto real con DeepSeek, ya con procedencia sellada

- Publicada `evidencia/piloto_deepseek_20261122_135846_5c1d7c/`, con el nombre de carpeta que
  produjo el programa, sin renombrar. 48 llamadas, todas HTTP 200, todos los campos de uso
  PRESENTE, cadena íntegra, ahorro 65,28 % / 65,39 % / 65,31 %.
- Es la primera bitácora que declara dentro del sello `fecha_utc` (2026-11-22T18:58:46Z),
  `version_modec_ce` 0.2.0, `commit` 32ad580 y `arbol_limpio`. Verificada en un equipo distinto
  del que la produjo: el verificador ya no añade los límites SIN FECHA ni SIN COMMIT, que sí
  sigue añadiendo sobre la bitácora del 2026-11-21.
- Reproducibilidad: con otro código y otros valores aleatorios, el acierto de caché (39,0 % y
  82,5 %) y el costo del brazo base (USD 0,0347) coinciden con los del 2026-11-21.
- **Corregida la afirmación sobre latencia.** El README decía «sin mejora: MODEC-CE tardó un 3 %
  más». Con las 6 corridas de los dos pilotos, MODEC-CE fue más rápido en 3 y más lento en 3
  (de −7,7 % a +3,1 %), así que lo que sostienen los datos es que **no hay efecto medible en
  latencia en ningún sentido**, no que la empeore. El beneficio sigue siendo de costo.
- Corregida la línea de cabecera del README, que describía la demo como «no incluye el piloto
  real» cuando desde este mismo ciclo sí lo incluye.

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
