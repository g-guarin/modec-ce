# Diseño del piloto de Super-Tokens

Estado: **propuesta, sin ejecutar**. Este documento se publica antes de escribir el código del
experimento y antes de conocer sus resultados. Su propósito es fijar por adelantado qué se va a
medir, con qué brazos y bajo qué criterios de éxito, de modo que el resultado no pueda elegirse
después.

## 1. Qué está demostrado hoy y qué no

Los tres pilotos publicados miden el efecto de la **disposición** del prompt sobre el acierto de
caché. No miden compresión: `modec_ce/piloto.py` planifica las llamadas con
`comprimir_historial=False`, y el historial se construye con `salida_sintetica`, no con respuestas
reales del modelo.

Los totales de entrada por brazo lo confirman:

| Piloto | Brazo | Entrada total |
|---|---|---|
| DeepSeek 2026-11-22 | `ingenua_rol` | 177 382 |
| DeepSeek 2026-11-22 | `modec` | 177 382 |
| Anthropic 2026-11-22 | `ingenua_rol` | 279 924 |
| Anthropic 2026-11-22 | `modec` | 279 940 |

La disposición MODEC-CE **no reduce el volumen de entrada**: lo redistribuye entre tokens
reutilizados y no reutilizados, y eso reduce el costo. Los 16 tokens de diferencia en Anthropic
sobre 279 924 no son evidencia de reducción.

La cifra C.1 de 75,6 % del README procede de `modec_ce/simulacion.py`, con el tokenizador
`aprox-regex-v1` y procedencia `DERIVED` sobre salidas sintéticas. Es una estimación de reducción
de texto en simulación, no una reducción medida de tokens facturados.

**Hueco que este piloto cierra:** si la sustitución del historial por Super-Tokens reduce los
tokens realmente enviados, cuánto, y a qué costo funcional.

## 2. Por qué importa más que el ahorro por caché

El ahorro por caché depende del proveedor: de su mecanismo y de su tarifa. Por eso dio 65,3 % con
DeepSeek y 60,1 % con Anthropic sobre la misma carga. Un lector puede preguntar, con razón, qué
ocurre con el suyo.

La reducción de tokens enviados no depende del proveedor. Menos tokens son menos tokens con
cualquier tarifa. Es una afirmación más fuerte, y por eso exige una medición más estricta.

## 3. Brazos

Diseño factorial 2×2: disposición × compresión. Las cuatro celdas se ejecutan sobre la misma
carga, el mismo modelo y la misma secuencia de pasos.

| Brazo | Disposición | Historial | Qué aísla |
|---|---|---|---|
| A | `ingenua_rol` | completo | línea base |
| B | `modec` | completo | efecto de la disposición (ya medido en los pilotos actuales) |
| C | `ingenua_rol` | Super-Tokens | efecto de la compresión, sin disposición |
| D | `modec` | Super-Tokens | efecto combinado |

Comparaciones declaradas de antemano:

- **A vs C** — reducción de tokens atribuible solo a la compresión.
- **B vs D** — la misma reducción bajo disposición MODEC.
- **A vs D** — efecto total del sistema completo.
- **C vs D** — si disposición y compresión interactúan o son aditivas.

El orden de los brazos se alterna entre corridas, como en los pilotos actuales. El valor volátil
por corrida se mantiene.

## 4. Cadena de ejecución real

Requisito que los pilotos actuales no cumplen y sin el cual la medición no significa nada.

El parámetro `salida_de` de `generar_peticiones` ya existe para esto y está documentado como
«permite usar salidas reales del modelo». El piloto no lo usa.

Secuencia por corrida:

1. El primer agente recibe el contexto completo y produce una **respuesta real**.
2. Esa respuesta se conserva íntegra como artefacto, con su SHA-256.
3. En el paso siguiente, los brazos A y B incorporan la respuesta completa; los brazos C y D
   incorporan su Super-Token.
4. Se repite durante todo el ciclo multiagente.

Sin esto se estaría comprimiendo texto sintético independiente y midiendo su longitud, que es lo
que ya hace la simulación.

**Consecuencia que hay que aceptar:** a partir del paso 2 los brazos dejan de tener contenido
idéntico. La comprobación `_contenido_identico` que protege los pilotos actuales **no es aplicable
aquí** y debe sustituirse por una comprobación distinta: que el paso 1 sí sea idéntico en los
cuatro brazos y que la divergencia posterior proceda únicamente de la compresión.

## 5. Medición de tokens

Se consolida por brazo, a partir de los campos que `proveedores.py` ya normaliza:

```
T_entrada = Σ (cache_read + cache_write + entrada_no_cache)
T_total   = T_entrada + T_salida
A_tokens  = 1 − (T_total del brazo comprimido / T_total del brazo completo)
```

Reglas:

- **Los tokens de caché cuentan como tokens procesados.** Tienen tarifa menor, no son gratis. No
  se deben confundir tokens procesados con tokens facturados a precio pleno.
- Se verifica la coherencia de los campos de uso de cada proveedor antes de aceptar la suma: si la
  suma declarada no cuadra con el total declarado, el registro se marca y la corrida se detiene,
  por el patrón P2 de centinela de presencia.
- El ahorro de **costo** se informa por separado del ahorro de **tokens**. Son dos magnitudes y
  confundirlas es el error que el repositorio existe para evitar.

## 6. Conservación funcional

La parte difícil, y la que decide si el resultado vale algo.

Un fragmento de 350 caracteres truncado más una lista de anclas **no es un resumen**. Es posible
que la compresión reduzca tokens y degrade la tarea. El experimento debe poder detectarlo.

Criterios, definidos antes de ejecutar:

| Criterio | Qué comprueba |
|---|---|
| Cumplimiento de la tarea | La salida final responde a lo pedido |
| Recuperación de hechos anteriores | Datos introducidos en pasos previos aparecen correctamente |
| Conservación de referencias | Las anclas `[H-nnn]` citadas siguen correspondiendo a su contenido |
| Ausencia de contradicciones nuevas | La salida no afirma lo contrario de un paso anterior |
| Respuesta sobre información omitida | Preguntas cuya respuesta cae **fuera** de los 350 caracteres conservados |
| Calidad de la respuesta final | Valoración global |

El quinto criterio es el que de verdad somete a prueba el mecanismo: si toda la información
necesaria cabe en los primeros 350 caracteres, la carga está mal diseñada para medir esto.

La evaluación se hace **a ciegas**: el evaluador no sabe qué brazo produjo cada salida. Si el
evaluador es un modelo, se declara cuál y se publica su prompt de evaluación.

## 7. Campos a sellar por llamada

Además de los que la cadena ya asienta:

| Campo | Función |
|---|---|
| `hash_artefacto_origen` | SHA-256 de la salida original completa |
| `hash_artefacto_comprimido` | SHA-256 del Super-Token |
| `tokens_entrada_informados` | Medición del proveedor |
| `tokens_salida_informados` | Medición del proveedor |
| `tokens_entrada_cache` | Reutilizados |
| `tokens_entrada_no_cache` | No reutilizados |
| `razon_compresion` | Reducción del historial en esa llamada |
| `resultado_tarea` | Resultado funcional |
| `resultado_fidelidad` | Resultado de la evaluación a ciegas |
| `proveedor`, `modelo`, `version` | Identidad del entorno |

La cadena P1/P2 y el anclaje RFC 3161 conservan integridad y procedencia temporal de este
experimento. **No validan su calidad semántica**, y la salida del verificador debe decirlo.

## 8. Un hueco del verificador que hay que cerrar antes

`herramientas/verificar_independiente.py` no menciona la compresión en ningún punto. Un tercero
que verifique una bitácora de los pilotos actuales no tiene forma de saber que Super-Tokens no
estuvo activo.

Por los estándares del propio repositorio, eso debe declararse: el verificador debe informar si la
bitácora corresponde a un piloto con historial completo o comprimido, y declararlo como límite
cuando el dato no esté en los registros.

## 9. Comparación con otros métodos del nicho

El nicho está activo y poblado. Las referencias relevantes al día de hoy:

- **LLMLingua y LLMLingua-2** (Microsoft Research, licencia MIT): compresión a nivel de token
  mediante un modelo pequeño que descarta tokens de baja información.
- **Selective-Context** y **LongLLMLingua**: usados como línea base en la propia literatura de
  LLMLingua-2.
- **RECOMP**: compresión por resumen extractivo.
- Compactación de historial para agentes de horizonte largo, con trabajo publicado en 2026.
- **Truncamiento y ventana deslizante**: la línea base trivial, y la más honesta de incluir.
- **Caché del proveedor**: no es compresión. Conserva el contexto y factura más barato lo repetido.

### Condiciones para que la comparación sea válida

1. **Ejecutar su código sobre esta carga.** Citar sus cifras publicadas no sirve: fueron medidas
   sobre otras cargas y otras tareas. Una comparación entre números obtenidos en condiciones
   distintas no es una comparación.
2. **Usar sus ajustes recomendados**, documentados y versionados. Si se eligen ajustes que los
   perjudican, el resultado no vale.
3. **Fijar la calidad, no la compresión.** Comparar razones de compresión sin control de calidad
   no mide nada: cualquier compresor alcanza el 90 % si la calidad es indiferente. La comparación
   se publica como frontera reducción–fidelidad, no como un número.
4. **Publicar el resultado adverso igual que el favorable.**

### Resultado esperado, declarado por adelantado

Sobre razón de compresión bruta, **es probable que Super-Tokens quede por detrás de LLMLingua-2**.
Es un mecanismo más simple: sustitución por referencia, truncamiento fijo y extracción de anclas,
frente a un clasificador entrenado de tokens.

Se declara aquí para que el resultado no se presente después como sorpresa ni se omita si
confirma esta expectativa.

La diferencia de MODEC-CE frente a esos métodos no está en la razón de compresión. Está en que la
reducción y su costo funcional quedan asentados en una cadena de evidencia sellada y anclada que
un tercero puede verificar sin ejecutar nada. Esa propiedad es la que se somete a prueba aquí, y
es independiente de quién comprima más.

## 10. Criterios de éxito, fijados antes de ejecutar

El piloto se considera concluyente —no exitoso, concluyente— si:

- Las cuatro celdas completan sus corridas sin registros AUSENTE.
- La suma de tokens declarada por el proveedor cuadra en todas las llamadas.
- La evaluación de fidelidad se hace a ciegas y con los seis criterios de la sección 6.
- El resultado se publica con su frontera reducción–fidelidad, cualquiera que sea.

Un resultado de la forma «la compresión reduce el contexto un X % y degrada la tarea un Y %» es un
resultado válido de este piloto y se publica como tal.
