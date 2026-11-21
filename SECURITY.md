# Seguridad

## Reportar una vulnerabilidad

No la describa en una incidencia pública. Use el reporte privado de GitHub (pestaña **Security → Report a vulnerability**). Indique:
- el módulo afectado;
- la garantía que se rompe (integridad de la cadena, fallo cerrado, fuga de claves o de contenido);
- un caso mínimo, sin claves reales.

## Límites declarados

- Según el autor, la cadena mínima integrada y el núcleo PESD **no han tenido revisión criptográfica por un especialista**.
- Sin un ancla externa, ninguna de las dos cadenas detecta que se trunque el final ni que se reescriba la cadena completa cuando no hay clave HMAC.
- Las claves de los proveedores se leen solo de variables de entorno. `piloto_proveedor.ps1` las pide de forma protegida y las borra al terminar.
- La URL inicial solo puede ser `https://…` o `http://127.0.0.1:<puerto>`, y no se siguen redirecciones.
