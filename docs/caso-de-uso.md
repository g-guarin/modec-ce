# Caso de uso: entregar una cifra de ahorro que el cliente pueda comprobar

> **Qué es este documento.** Un ejemplo trabajado de cómo se ve una entrega hecha con MODEC-CE,
> construido con la bitácora **real** del piloto del propio proyecto
> ([`evidencia/piloto_deepseek_20261122_135846_5c1d7c/`](../evidencia/piloto_deepseek_20261122_135846_5c1d7c/)).
> No hay cliente, encargo ni consultoría reales: el escenario es ilustrativo y las cifras son las
> que están publicadas en este repositorio. Todo lo que aquí se afirma de esos números se puede
> comprobar con los comandos que aparecen más abajo.

## El problema

Una consultoría reordena los prompts de la orquestación multiagente de un cliente para aprovechar
el caché de prefijos del proveedor, y presenta el resultado:

> «Redujimos el costo de inferencia un 65 %.»

El cliente no tiene forma de comprobarlo. Puede pedir la hoja de cálculo, pero la hizo la misma
parte que cobra por el resultado. Y no hace falta mala fe para que esa cifra se desvíe:

- se mide la carga que mejor funciona, no la que el cliente ejecuta de verdad;
- se compara contra una línea base débil, elegida para que la mejora parezca mayor;
- se mide en la franja tarifaria que más conviene;
- la corrida que salió mal no aparece en la hoja;
- un campo que el proveedor no informó se cuenta como cero y mejora el resultado.

Ninguna de esas cosas es fraude, y todas cambian el número. El problema no es la honestidad de
quien entrega: es que **la cifra no es comprobable**, y por tanto no es discutible.

## La entrega

En vez de una hoja de cálculo, se entregan tres cosas:

1. **La bitácora sellada.** 50 registros encadenados por digest: el plan, las 48 llamadas y el
   resumen. No contiene prompts, respuestas ni claves — solo huellas, conteos, latencias y costos.
2. **El comando para verificarla**, que el cliente corre en su máquina, sin instalar nada.
3. **El informe**, cuyas cifras salen de esa bitácora y de ninguna otra parte.

### Resultado

| Medida | `ingenua_rol` (línea base) | `modec` | |
|---|---|---|---|
| Llamadas medidas | 24 | 24 | |
| Tokens de entrada servidos desde caché | **38,97 %** | **82,48 %** | informado por DeepSeek |
| Costo de las 3 corridas, tarifa pico | USD 0,034737 | USD 0,012044 | derivado de tarifa declarada |
| Costo de las 3 corridas, tarifa reducida | USD 0,017368 | USD 0,006022 | ídem |
| Latencia total | 41,7 s | 41,9 s | medido |

**Ahorro por corrida: 65,28 % · 65,39 % · 65,31 %** (media 65,33 %, tres corridas válidas).

Sobre la latencia, el informe dice lo que midió y no más: +2,9 %, +3,1 % y −7,7 % según la
corrida. Con los dos pilotos publicados son seis corridas, tres a favor y tres en contra. **No hay
efecto medible en velocidad, en ninguna dirección.** Una entrega que prometiera también mejora de
latencia estaría afirmando algo que estos datos no sostienen.

### Procedencia, cifra por cifra

| | Origen |
|---|---|
| Tokens de acierto y fallo de caché | **MEDIDO**: campo `usage` de la respuesta del proveedor |
| Costo | **DERIVADO**: tokens medidos × tarifa de `datos/precios.json`, fechada y con su fuente |
| Latencia | **MEDIDO** en el cliente, incluye red |
| Ahorro | **DERIVADO** de los costos anteriores |
| Factura real del proveedor | **NO INCLUIDA**: el costo derivado no es la factura y debe contrastarse con el panel de uso |

## Lo que el cliente comprueba en dos minutos

Sin instalar nada. Solo Python y el repositorio:

```bash
python herramientas/verificar_independiente.py evidencia/piloto_deepseek_20261122_135846_5c1d7c
```

Salida:

<!-- SALIDA-VERIFICADOR -->
```json
{
  "registros": 50,
  "llamadas": 48,
  "ancla_externa": "PRESENTE_Y_CORRESPONDE_A_ESTA_CADENA",
  "fecha_declarada_utc": "2026-11-22T18:58:46Z",
  "version_declarada": "0.2.0",
  "commit_declarado": "32ad580f09912f32242e3a1510d1e8985b07df53",
  "arbol_limpio": true,
  "autenticidad": "NO_EVALUADA (sin clave)",
  "tarifa_usada": ["peak"],
  "ahorro_recalculado_por_corrida": {"1": 0.6528, "2": 0.6539, "3": 0.6531},
  "integra": true,
  "fallos": [],
  "limites": [
    "ANCLA PRESENTE en piloto_deepseek_20261122_135846_5c1d7c: contiene el digest final de esta cadena, pero la FIRMA de la autoridad no se comprueba aquí. Compruébela con: openssl ts -verify -in ancla.tsr -queryfile ancla.tsq -CAfile cacert.pem -untrusted tsa.crt",
    "SIN CLAVE HMAC: integridad, no autoría",
    "TARIFA: el ahorro se recalcula con la más cara de cada registro (peak); con otra tarifa del mismo proveedor el ahorro cambia, y la bitácora no juzga cuál le corresponde a usted"
  ]
}
```
<!-- /SALIDA-VERIFICADOR -->

Una prueba comprueba que este bloque coincide con lo que la herramienta imprime hoy. Un documento que enseña una salida que el programa ya no produce es exactamente el defecto que este proyecto existe para no tener.

Qué acaba de verificar, sin fiarse de nadie:

- **Que el 65 % no es una cifra copiada en un informe**, sino el resultado de volver a sumar los
  costos registrados en las 48 llamadas, una por una.
- **Que no falta ninguna corrida.** Los 50 registros están numerados y cada uno lleva el digest del
  anterior: borrar la corrida que salió mal rompe la cadena y el verificador lo dice.
- **Que nada se retocó después.** Cambiar un solo número invalida su digest.
- **Cuándo se midió y con qué código**, porque la fecha, la versión y el commit viajan dentro del
  sello, no en el nombre de una carpeta que cualquiera puede renombrar.
- **Que esa cadena ya existía antes de una fecha que no pone el autor**, porque un sello de tiempo
  RFC 3161 de una autoridad independiente lo acredita, y la herramienta comprueba que ese sello
  corresponde a esta cadena y no a otra.

Y, lo más importante para la confianza: **la herramienta declara lo que no puede comprobar**. Los
límites de la salida no son letra pequeña, son parte del resultado. Fíjese en que sobre el ancla
dice que no verifica la firma de la autoridad, en vez de callarlo.

## Lo que esto sigue sin probar

Conviene decirlo en la entrega, no esperar a que lo pregunten:

- **Autoría.** Sin clave HMAC se comprueba integridad, no quién selló. Y el HMAC es simétrico: solo
  prueba autoría ante quien ya tiene la clave. Para autoría verificable por terceros hace falta
  firma asimétrica.
- **La firma del ancla, con esta herramienta.** El ancla temporal existe y está verificada (ver
  `sello/`), y eso cierra la reescritura completa: quien rehiciera la bitácora ya no podría hacer
  que cuadrara con un sello que no puede falsificar. Pero `verificar_independiente.py` solo
  comprueba que el ancla corresponde a esta cadena; **validar la firma de la autoridad exige
  `openssl ts -verify`**, porque leer ASN.1 traería dependencias. Está dicho en su salida.
  Una bitácora sin ancla —como la del 2026-11-21— sigue siendo reescribible sin dejar rastro, y la
  herramienta lo declara sobre ella.
- **Que la carga medida se parezca a la del cliente.** Esto no lo resuelve ninguna criptografía, y
  es lo que más cambia el número. Ver abajo.

## Por qué el cliente debe exigir que se mida *su* carga

El ahorro actúa solo sobre la entrada. Cuanto más largo es lo que el modelo escribe, menos pesa la
entrada en la factura. Con las tasas de acierto exactamente medidas en este piloto y sin cambiar
nada más:

| Salida por llamada | Ahorro | La entrada es, de la factura |
|---|---|---|
| 64 tokens | 65,1 % | 94 % |
| 500 | 47,2 % | 68 % |
| 2 000 | 24,2 % | 35 % |
| 5 000 | 12,3 % | 18 % |

La misma técnica, el mismo acierto de caché, y el ahorro va del 65 % al 12 %. Por eso **un
porcentaje tomado de otro encargo no sirve para decidir**, por bien medido que esté. Lo que se
puede transferir no es la cifra: es el procedimiento.

Reprodúzcala con `python -m modec_ce sensibilidad`.

## Cómo medir la propia carga

```bash
# 1. Ver el plan y la cota de costo, sin tocar la red
python -m modec_ce piloto --proveedor deepseek

# 2. Ejecutarlo de verdad (en Windows, piloto_proveedor.ps1 pide la clave de forma protegida)
python -m modec_ce piloto --proveedor deepseek --ejecutar --confirmar EJECUTAR-PILOTO

# 3. Verificar lo que salió
python herramientas/verificar_independiente.py resultados/<carpeta>
```

La carga sintética del repositorio se configura en `modec_ce/carga.py`. Para que la medición diga
algo sobre un caso real, hay que acercarla a él: número de agentes, pasos, tamaño del contexto
estable y, sobre todo, **longitud de las salidas**.

Los adaptadores de Anthropic, OpenAI y OpenRouter solo se han probado con respuestas simuladas, no
con llamadas reales. Quien los use primero debería decirlo en su entrega.
