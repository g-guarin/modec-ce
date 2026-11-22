# Seguridad

## Reportar una vulnerabilidad

No la describa en una incidencia pública. Use el reporte privado de GitHub (pestaña **Security → Report a vulnerability**). Indique:
- el módulo afectado;
- la garantía que se rompe (integridad de la cadena, fallo cerrado, fuga de claves o de contenido);
- un caso mínimo, sin claves reales.

## Límites declarados

- Según el autor, la cadena mínima integrada y el núcleo PESD **no han tenido revisión criptográfica por un especialista**.
- Sin un ancla externa, ninguna de las dos cadenas detecta que se trunque el final ni que se reescriba la cadena completa cuando no hay clave HMAC.
- **La fecha del sello la declara el equipo que ejecuta el piloto**, no un tercero. Desde 0.2.0 viaja dentro del payload (con la versión y el commit), de modo que queda cubierta por el digest y no se puede cambiar sin romper la cadena; pero acredita una hora declarada, no certificada. El sello de tiempo RFC 3161 sobre el `digest` del último registro es lo que la vuelve verificable por terceros. La bitácora publicada con 0.1.0 no trae ninguno de esos campos, y el verificador lo declara como límite en su salida.
- **La verificación con clave es estricta a propósito**: exige `key_id` esperado y HMAC válido en todos los registros. Sin esa exigencia la autenticidad sería degradable, porque `key_id` va dentro del cuerpo digestado y podría quitarse de toda la cadena recalculando los digest. La clave es la declaración de qué firma se espera: si no se entrega, solo se comprueba integridad y una cadena sin firmas verifica igual.
- El presupuesto se comprueba después de cada llamada, así que puede excederse por el costo de una llamada como máximo; la cota preflight, que trata toda la entrada como no cacheada a la tarifa más alta, es la que impide arrancar un plan que no cabe.
- Las claves de los proveedores se leen solo de variables de entorno. `piloto_proveedor.ps1` las pide de forma protegida y las borra al terminar.
- La URL inicial solo puede ser `https://…` o `http://127.0.0.1:<puerto>`, y no se siguen redirecciones.
