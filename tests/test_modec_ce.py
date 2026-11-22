import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import modec_ce  # noqa: E402
from modec_ce import informe, nucleo, procedencia, simulacion, tokens  # noqa: E402
from modec_ce.cache import ModeloCachePrefijos  # noqa: E402
from modec_ce.carga import DISPOSICIONES, ConfigCarga, generar_peticiones, supertoken  # noqa: E402
from modec_ce.costo import cargar_tarifa  # noqa: E402
from modec_ce.evidencia import CadenaEvidencia, presencia_uso, uso_evaluable  # noqa: E402
from modec_ce.piloto import CONFIRMACION, LimitesPiloto, ejecutar_piloto, planificar, transporte_urllib  # noqa: E402
from modec_ce.proveedores import PROVEEDORES  # noqa: E402

A = "fundación común del sistema " * 20
B, C, D = " bloque be " * 5, " bloque ce " * 5, " bloque de " * 5
CFG_PEQUENA = ConfigCarga(pasos=2, agentes=("a", "b"), tokens_corpus=600, tokens_salida_agente=100, secciones_corpus=4)


class ReglasCacheDocumentadasTests(unittest.TestCase):
    """Ejemplos 1 y 2 de https://api-docs.deepseek.com/guides/kv_cache/."""

    def test_ejemplo_1_la_segunda_peticion_acierta_el_prefijo_almacenado(self):
        m = ModeloCachePrefijos()
        self.assertEqual(m.procesar(A + B).tokens_acierto, 0)
        self.assertEqual(m.procesar(A + B + C).tokens_acierto, tokens.contar(A + B))

    def test_ejemplo_2_prefijo_comun_acierta_desde_la_tercera(self):
        m = ModeloCachePrefijos()
        m.procesar(A + B)
        self.assertEqual(m.procesar(A + C).tokens_acierto, 0)
        tercera = m.procesar(A + D)
        self.assertGreaterEqual(tercera.tokens_acierto, tokens.contar(A))
        self.assertLess(tercera.tokens_acierto, tokens.contar(A + D))

    def test_sin_prefijo_comun_no_hay_acierto(self):
        m = ModeloCachePrefijos()
        m.procesar("uno " + A)
        self.assertEqual(m.procesar("dos " + A).tokens_acierto, 0)


class CargaTests(unittest.TestCase):
    def test_las_disposiciones_tienen_el_mismo_contenido(self):
        huellas = {d: [p.huella_contenido for p in generar_peticiones(CFG_PEQUENA, d, comprimir_historial=False)]
                   for d in DISPOSICIONES}
        valores = list(huellas.values())
        self.assertTrue(all(v == valores[0] for v in valores))

    def test_modec_ordena_de_lo_estable_a_lo_variable(self):
        self.assertEqual(DISPOSICIONES["modec"][0], "FUNDACION")
        self.assertEqual(DISPOSICIONES["modec"][-1], "VOLATIL")

    def test_supertoken_acota_resumen_y_referencia_sha256(self):
        st = supertoken("a", 1, "x" * 1000 + " [H-001]")
        self.assertLessEqual(len(st.resumen), 350)
        self.assertTrue(st.uri.startswith("artifact://sha256:"))
        self.assertEqual(st.anclas, ("[H-001]",))


class CostoTests(unittest.TestCase):
    def test_costo_decimal(self):
        t = cargar_tarifa("deepseek-flash", "peak")
        self.assertEqual(t.costo(1_000_000, 1_000_000, 1_000_000), Decimal("0.006") + Decimal("0.30") + Decimal("1.20"))

    def test_escritura_de_cache_anthropic(self):
        t = cargar_tarifa("claude-haiku-5-5", proveedor="anthropic")
        self.assertEqual(t.costo(0, 0, 0, 1_000_000), Decimal("0.125"))

    def test_conteos_invalidos(self):
        t = cargar_tarifa()
        with self.assertRaises(ValueError):
            t.costo(-1, 0, 0)
        with self.assertRaises(ValueError):
            t.costo(True, 0, 0)


class PresenciaP2Tests(unittest.TestCase):
    def test_campo_de_cache_ausente_no_es_cero(self):
        uso = {"prompt_tokens": 10, "completion_tokens": 2}
        self.assertEqual(presencia_uso(uso)["prompt_cache_hit_tokens"], "AUSENTE")
        self.assertFalse(uso_evaluable(uso))

    def test_cero_presente_es_evaluable(self):
        uso = {"prompt_tokens": 10, "completion_tokens": 2, "prompt_cache_hit_tokens": 0,
               "prompt_cache_miss_tokens": 10}
        self.assertTrue(uso_evaluable(uso))


class NormalizacionProveedoresTests(unittest.TestCase):
    def test_openai_resta_cache_de_la_entrada(self):
        u = PROVEEDORES["openai"].normalizar(
            {"prompt_tokens": 2000, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 1536}})
        self.assertEqual((u.acierto, u.fallo, u.salida, u.evaluable), (1536, 464, 5, True))

    def test_openai_sin_detalle_de_cache_no_es_evaluable(self):
        self.assertFalse(PROVEEDORES["openai"].normalizar({"prompt_tokens": 10, "completion_tokens": 1}).evaluable)

    def test_anthropic_separa_lectura_y_escritura(self):
        u = PROVEEDORES["anthropic"].normalizar({"input_tokens": 50, "output_tokens": 7,
                                                 "cache_read_input_tokens": 3000, "cache_creation_input_tokens": 900})
        self.assertEqual((u.acierto, u.escritura, u.fallo, u.salida), (3000, 900, 50, 7))

    def test_anthropic_marca_puntos_de_cache_iguales_en_todos_los_brazos(self):
        cuerpo = PROVEEDORES["anthropic"].cuerpo("m", ["h", "s1", "s2", "s3", "s4"], 10, {})
        marcados = [i for i, b in enumerate(cuerpo["messages"][0]["content"]) if "cache_control" in b]
        self.assertEqual(marcados, [2, 3])

    def test_openrouter_conserva_el_costo_informado(self):
        u = PROVEEDORES["openrouter"].normalizar({"prompt_tokens": 100, "completion_tokens": 1, "cost": 0.0001,
                                                  "prompt_tokens_details": {"cached_tokens": 64}})
        self.assertEqual(u.costo_plataforma, "0.000100000")


class EvidenciaTests(unittest.TestCase):
    def test_cadena_integra_y_deteccion_de_manipulacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "evidencia.jsonl"
            cadena = CadenaEvidencia(ruta)
            for i in range(3):
                cadena.asentar({"indice": i, "acierto": 100 * i})
            self.assertTrue(cadena.verificar()["integra"])
            lineas = ruta.read_text(encoding="utf-8").splitlines()
            lineas[1] = lineas[1].replace('"acierto":100', '"acierto":999')
            ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
            self.assertFalse(CadenaEvidencia(ruta).verificar()["integra"])


def transporte_simulado(estado=200, sin_cache=False):
    modelo = ModeloCachePrefijos()

    def enviar(url, cabeceras, cuerpo, timeout):
        datos = json.loads(cuerpo.decode("utf-8"))
        texto = "".join(m["content"] for m in datos["messages"])
        if estado != 200:
            return estado, json.dumps({"error": {"type": "invalid_request_error", "message": "x"}}).encode()
        r = modelo.procesar(texto)
        uso = {"prompt_tokens": r.tokens_entrada, "completion_tokens": 10}
        if not sin_cache:
            uso.update(prompt_cache_hit_tokens=r.tokens_acierto, prompt_cache_miss_tokens=r.tokens_fallo)
        return 200, json.dumps({"choices": [{"message": {"content": "ok"}}], "usage": uso}).encode()
    return enviar


class PilotoTests(unittest.TestCase):
    def _ejecutar(self, tmp, **kw):
        base = dict(carpeta_resultados=Path(tmp), clave="clave-de-prueba", confirmacion=CONFIRMACION,
                    transporte=transporte_simulado(), cfg=CFG_PEQUENA, dormir=lambda s: None)
        base.update(kw)
        return ejecutar_piloto(**base)

    def test_contenido_distinto_entre_brazos_detiene_sin_llamadas(self):
        from unittest import mock
        llamadas: list[int] = []

        def transporte(*a, **k):
            llamadas.append(1)
            return 200, b"{}"

        with tempfile.TemporaryDirectory() as tmp, mock.patch("modec_ce.piloto._contenido_identico",
                                                              return_value=False):
            with self.assertRaises(ValueError):
                self._ejecutar(tmp, transporte=transporte)
            self.assertEqual(llamadas, [])

    def test_sin_confirmacion_no_hay_llamadas(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(PermissionError):
            self._ejecutar(tmp, confirmacion="")

    def test_presupuesto_insuficiente_bloquea_antes_de_llamar(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(PermissionError):
            self._ejecutar(tmp, limites=LimitesPiloto(presupuesto_usd=Decimal("0.000001")))

    def test_tres_corridas_miden_ahorro_y_sellan_sin_guardar_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._ejecutar(tmp)
            self.assertIsNone(res.detenido)
            resumen = json.loads((res.carpeta / "resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(resumen["ahorro_relativo"]["corridas_validas"], 3)
            self.assertGreater(resumen["ahorro_relativo"]["min"], 0.0)
            self.assertTrue(resumen["verificacion"]["integra"])
            evidencia = (res.carpeta / "evidencia.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("CORPUS COMPARTIDO", evidencia)
            self.assertNotIn("clave-de-prueba", evidencia)

    def test_el_sello_declara_fecha_version_y_commit(self):
        """Sin fecha ni versión dentro del payload, un tercero no puede fechar la bitácora
        ni atarla a una versión publicada del código."""
        with tempfile.TemporaryDirectory() as tmp:
            res = self._ejecutar(tmp)
            registros = [json.loads(x) for x in
                         (res.carpeta / "evidencia.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
            plan = next(r["payload"] for r in registros if r["payload"]["tipo"] == "PLAN")
            self.assertRegex(plan["fecha_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertEqual(plan["version_modec_ce"], modec_ce.__version__)
            self.assertIn("commit", plan)
            self.assertIn("arbol_limpio", plan)
            llamadas = [r["payload"] for r in registros if r["payload"]["tipo"] == "LLAMADA"]
            self.assertTrue(llamadas)
            for ll in llamadas:
                self.assertRegex(ll["instante_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            resumen = json.loads((res.carpeta / "resumen.json").read_text(encoding="utf-8"))
            self.assertRegex(resumen["fecha_utc_cierre"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_uso_sin_campos_de_cache_detiene(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._ejecutar(tmp, transporte=transporte_simulado(sin_cache=True))
            self.assertIn("P2", res.detenido)
            self.assertEqual(len(res.llamadas), 1)

    def test_error_http_detiene(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._ejecutar(tmp, transporte=transporte_simulado(estado=400))
            self.assertIsNotNone(res.detenido)
            self.assertEqual(len(res.llamadas), 1)

    def test_plan_intercala_alterna_y_conserva_contenido(self):
        plan = planificar(("ingenua_rol", "modec"), CFG_PEQUENA, nonces=["n1", "n2"])
        primera = [p for p in plan if p.corrida == 1][:2]
        segunda = [p for p in plan if p.corrida == 2][:2]
        self.assertEqual([p.brazo for p in primera], ["ingenua_rol", "modec"])
        self.assertEqual([p.brazo for p in segunda], ["modec", "ingenua_rol"])
        self.assertTrue(all(p.segmentos[0] == f"EJECUCIÓN n{p.corrida}" for p in plan))
        for c in (1, 2):
            a = [p.huella_contenido for p in plan if p.brazo == "ingenua_rol" and p.corrida == c]
            b = [p.huella_contenido for p in plan if p.brazo == "modec" and p.corrida == c]
            self.assertEqual(a, b)

    def test_transporte_rechaza_destinos_no_permitidos(self):
        with self.assertRaises(PermissionError):
            transporte_urllib("http://ejemplo.com/x", {}, b"{}", 1)

    def test_transporte_no_sigue_redirecciones(self):
        """Una redirección no debe reenviar la cabecera Authorization a otro destino."""
        import http.server
        recibidas: list[str] = []

        class Base(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def _responder(self, codigo, cabeceras=()):
                # Leer el cuerpo antes de responder: si se cierra la conexión con datos sin
                # leer, Windows la aborta y el cliente no llega a ver la respuesta.
                pendiente = int(self.headers.get("Content-Length") or 0)
                if pendiente:
                    self.rfile.read(pendiente)
                self.send_response(codigo)
                for k, v in cabeceras:
                    self.send_header(k, v)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        class Destino(Base):
            def do_POST(self):
                recibidas.append(self.headers.get("Authorization", ""))
                self._responder(200)

            do_GET = do_POST

        destino = http.server.HTTPServer(("127.0.0.1", 0), Destino)
        puerto_destino = destino.server_address[1]

        class Origen(Base):
            def do_POST(self):
                self._responder(302, [("Location", f"http://127.0.0.1:{puerto_destino}/robo")])

        origen = http.server.HTTPServer(("127.0.0.1", 0), Origen)
        for s in (destino, origen):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            estado, _ = transporte_urllib(f"http://127.0.0.1:{origen.server_address[1]}/x",
                                          {"Authorization": "Bearer secreto"}, b"{}", 5)
            self.assertEqual(estado, 302)
            self.assertEqual(recibidas, [])
        finally:
            for s in (destino, origen):
                s.shutdown()
                s.server_close()


@unittest.skipUnless(importlib.util.find_spec("torch"), "requiere torch (opcional)")
class ServidorLocalTests(unittest.TestCase):
    def test_piloto_por_http_contra_transformador_local(self):
        from modec_ce.servidor_local import ServicioLocal, crear_servidor
        servidor = crear_servidor(ServicioLocal())
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                res = ejecutar_piloto(proveedor="local", corridas=1, cfg=CFG_PEQUENA, carpeta_resultados=Path(tmp),
                                      confirmacion=CONFIRMACION, puerto_local=servidor.server_address[1],
                                      limites=LimitesPiloto(pausa_s=0))
                self.assertIsNone(res.detenido)
                aciertos = {b: sum(f["acierto"] for f in res.llamadas if f["brazo"] == b) for b in ("ingenua_rol", "modec")}
                self.assertGreater(aciertos["modec"], aciertos["ingenua_rol"])
        finally:
            servidor.shutdown()
            servidor.server_close()


class SimulacionTests(unittest.TestCase):
    def test_modec_reduce_costo_frente_a_ambas_lineas_base(self):
        sim = simulacion.ejecutar(ConfigCarga(pasos=2, agentes=("a", "b", "c"), tokens_corpus=1500))
        self.assertTrue(sim["contenido_identico_entre_disposiciones"])
        for clave, valor in sim["ahorro_relativo"].items():
            self.assertGreater(valor["peak"], 0.0, clave)


RAIZ = Path(__file__).resolve().parents[1]


class CadenaMinimaTests(unittest.TestCase):
    """Cadena integrada que se usa cuando pesd-nucleo no está disponible (clon público)."""

    def _cadena(self, clave=None):
        return nucleo.CadenaMinima(clave, "modec-ce")

    def test_cadena_integra_y_detecta_alteracion_borrado_y_reorden(self):
        c = self._cadena()
        regs, ant = [], None
        for i in range(4):
            ant = c.sellar({"i": i, "acierto": 0 if i == 0 else 10 * i}, ant)
            regs.append(ant)
        self.assertEqual(c.verificar(regs)[0], [])
        alterado = [nucleo.RegistroMinimo.desde_json(r.a_json()) for r in regs]
        alterado[1].payload["acierto"] = 999
        self.assertTrue(any("alterado" in m for m in c.verificar(alterado)[0]))
        self.assertTrue(any("hash_previo" in m for m in c.verificar(regs[:1] + regs[2:])[0]))
        self.assertTrue(c.verificar([regs[1], regs[0]] + regs[2:])[0])

    def test_hmac_detecta_clave_distinta(self):
        clave = bytes(range(32))
        r = self._cadena(clave).sellar({"x": 1}, None)
        self.assertEqual(self._cadena(clave).verificar([r])[0], [])
        self.assertTrue(self._cadena(bytes(32)).verificar([r])[0])
        self.assertTrue(self._cadena(None).verificar([r])[0])

    def test_modo_estricto_rechaza_una_cadena_a_la_que_le_quitaron_las_firmas(self):
        """`key_id` va dentro del cuerpo digestado: quien reescriba la cadena puede quitar
        `key_id` y `hmac` de todos los registros y recalcular los digest. Con clave, eso
        debe fallar; si no, la autenticidad sería degradable sin dejar rastro."""
        clave = bytes(range(32))
        c = self._cadena(clave)
        regs, ant = [], None
        for i in range(3):
            ant = c.sellar({"i": i}, ant)
            regs.append(ant)
        self.assertEqual(c.verificar(regs)[0], [])

        sin_firma, previo = [], None                      # reescritura completa sin firmas, digest recalculados
        plano = nucleo.CadenaMinima(None, "modec-ce")
        for r in regs:
            previo = plano.sellar(r.payload, previo)
            sin_firma.append(previo)
        self.assertEqual(plano.verificar(sin_firma)[0], [])          # sin clave: pasa, es solo integridad
        motivos = c.verificar(sin_firma)[0]                          # con clave: debe reclamar lo ausente
        self.assertTrue(motivos)
        self.assertTrue(all("sin HMAC" in m for m in motivos), motivos)

    def test_modo_estricto_rechaza_key_id_inesperado(self):
        clave = bytes(range(32))
        r = nucleo.CadenaMinima(clave, "otro-firmante").sellar({"x": 1}, None)
        self.assertTrue(any("key_id" in m for m in self._cadena(clave).verificar([r])[0]))

    def test_sin_clave_el_limite_declara_que_la_autenticidad_no_se_evaluo(self):
        limites = self._cadena(None).verificar([self._cadena(None).sellar({"x": 1}, None)])[1]
        self.assertTrue(any("SIN CLAVE" in x for x in limites), limites)


class TablaSalidaTests(unittest.TestCase):
    """La tabla del README que muestra cómo cae el ahorro al alargar la salida es el argumento
    central del posicionamiento del repositorio. Si se desfasa del código, el repositorio estaría
    haciendo exactamente lo que critica: publicar una cifra que nadie puede reproducir."""

    RUTA = Path(__file__).resolve().parents[1] / "README.md"

    def test_la_tabla_del_readme_coincide_con_el_codigo(self):
        texto = self.RUTA.read_text(encoding="utf-8")
        bloque = texto.split("<!-- SALIDA -->")[1].split("<!-- /SALIDA -->")[0]
        for fila in simulacion.sensibilidad_salida()["filas"]:
            salida = f"{fila['salida_por_llamada']:,}".replace(",", " ")
            ahorro = f"{100 * fila['ahorro']:.1f}".replace(".", ",")
            entrada = f"{round(100 * fila['entrada_en_la_factura'])}"
            self.assertIn(f"| {ahorro} % | {entrada} % |", bloque,
                          f"la fila de salida={salida} no coincide con el código")

    def test_el_ahorro_cae_al_alargar_la_salida(self):
        filas = simulacion.sensibilidad_salida()["filas"]
        ahorros = [f["ahorro"] for f in filas]
        self.assertEqual(ahorros, sorted(ahorros, reverse=True))
        self.assertGreater(ahorros[0], 0.6)
        self.assertLess(ahorros[-1], 0.2)


class GitignoreSelloTests(unittest.TestCase):
    """La regla `*.pem` excluía en silencio el certificado de la autoridad de sellado, que sí debe
    publicarse junto al ancla. Un archivo que no llega al repositorio sin decir nada es el tipo de
    fallo que este proyecto existe para no tener."""

    RAIZ = Path(__file__).resolve().parents[1]

    def _ignorado(self, ruta: str) -> bool:
        r = subprocess.run(("git", "-C", str(self.RAIZ), "check-ignore", "-q", ruta),
                           capture_output=True)
        return r.returncode == 0

    def test_los_certificados_del_sello_se_publican_y_las_claves_no(self):
        if subprocess.run(("git", "-C", str(self.RAIZ), "rev-parse"), capture_output=True).returncode:
            self.skipTest("sin repositorio git disponible")
        for publicable in ("sello/x/cacert.pem", "sello/x/tsa.crt"):
            self.assertFalse(self._ignorado(publicable), f"{publicable} quedaría fuera del repositorio")
        for secreto in ("sello/x/privada.key", ".env", "clave.pem"):
            self.assertTrue(self._ignorado(secreto), f"{secreto} podría publicarse por error")


class LatenciaInformeTests(unittest.TestCase):
    """La ficha de latencia mostraba el peor dato de las corridas como si fuera el resultado.
    Elegir el dato desfavorable es el mismo error que elegir el favorable."""

    def test_muestra_el_rango_y_no_un_extremo(self):
        self.assertEqual(informe._rango_latencia([-0.077, 0.029, 0.031]), "-7.7% a 3.1%")
        self.assertEqual(informe._rango_latencia([0.02]), "2.0%")
        self.assertEqual(informe._rango_latencia([]), "—")

    def test_la_pagina_no_titula_la_latencia_con_un_solo_extremo(self):
        from modec_ce import cli
        pilotos = cli._recoger_pilotos()
        if not pilotos:
            self.skipTest("sin bitácoras")
        pagina = informe.generar_html(simulacion.ejecutar(), pilotos)
        self.assertNotIn("reducción mínima de latencia", pagina)
        self.assertIn("dispersión, no efecto", pagina)
        for p in pilotos:
            lat = [d["reduccion_latencia"] for d in (p.get("corridas") or {}).values()
                   if d.get("reduccion_latencia") is not None]
            if len(lat) > 1 and min(lat) != max(lat):
                self.assertIn(informe._rango_latencia(lat), pagina)


class CasoDeUsoTests(unittest.TestCase):
    """El caso de uso presenta cifras como si fueran una entrega a un cliente. Si se desfasaran de
    la bitácora publicada, el repositorio estaría haciendo lo mismo que el documento critica:
    presentar un número que no sale de la evidencia que dice respaldarlo."""

    RUTA = Path(__file__).resolve().parents[1] / "docs" / "caso-de-uso.md"
    BITACORA = (Path(__file__).resolve().parents[1] / "evidencia"
                / "piloto_deepseek_20261122_135846_5c1d7c" / "resumen.json")

    def test_las_cifras_salen_de_la_bitacora_publicada(self):
        if not self.RUTA.exists() or not self.BITACORA.exists():
            self.skipTest("sin caso de uso o sin bitácora")
        texto = self.RUTA.read_text(encoding="utf-8")
        d = json.loads(self.BITACORA.read_text(encoding="utf-8"))

        def coma(x: str) -> str:
            return x.replace(".", ",")

        for brazo in ("ingenua_rol", "modec"):
            b = d["brazos"][brazo]
            self.assertIn(coma(f"{100 * b['tasa_acierto']:.2f}"), texto, f"tasa de {brazo}")
            for franja in ("peak", "offpeak"):
                self.assertIn(coma(f"{Decimal(b['costos_usd'][franja]):.6f}"), texto,
                              f"costo {franja} de {brazo}")
            self.assertIn(coma(f"{b['latencia_total_ms'] / 1000:.1f}"), texto, f"latencia de {brazo}")

        for corrida in d["corridas"].values():
            self.assertIn(coma(f"{100 * corrida['ahorro_relativo']:.2f}"), texto)
        self.assertIn(coma(f"{100 * d['ahorro_relativo']['media']:.2f}"), texto)
        # El documento debe señalar de qué bitácora salen las cifras, no solo citarlas.
        self.assertIn(self.BITACORA.parent.name, texto)

    def test_declara_que_el_escenario_es_ilustrativo(self):
        """Un informe de ejemplo que no se declara como tal es un registro fabricado."""
        if not self.RUTA.exists():
            self.skipTest("sin caso de uso")
        texto = self.RUTA.read_text(encoding="utf-8").lower()
        self.assertIn("no hay cliente", texto)
        self.assertIn("ilustrativo", texto)


class CitacionTests(unittest.TestCase):
    RUTA = Path(__file__).resolve().parents[1] / "CITATION.cff"

    def test_la_version_citada_no_se_desfasa_del_codigo(self):
        """Un archivo de citación con una versión vieja cita algo que no es lo que hay."""
        if not self.RUTA.exists():
            self.skipTest("sin CITATION.cff")
        texto = self.RUTA.read_text(encoding="utf-8")
        version = next((x.split(":", 1)[1].strip() for x in texto.splitlines()
                        if x.startswith("version:")), None)
        self.assertEqual(version, modec_ce.__version__)
        for campo in ("cff-version:", "title:", "authors:", "license:", "repository-code:"):
            self.assertIn(campo, texto)

    def test_no_publica_datos_de_contacto_personales(self):
        """El repositorio enruta el contacto por el reporte privado de GitHub; el archivo de
        citación no debe filtrar un correo personal."""
        if not self.RUTA.exists():
            self.skipTest("sin CITATION.cff")
        texto = self.RUTA.read_text(encoding="utf-8")
        self.assertNotIn("@gmail", texto)
        self.assertFalse([x for x in texto.splitlines()
                          if x.strip().startswith("email:") and not x.strip().startswith("#")])


class ProcedenciaTests(unittest.TestCase):
    def test_sello_corrida_declara_fecha_version_y_estado_del_arbol(self):
        s = procedencia.sello_corrida()
        self.assertRegex(s["fecha_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(s["version_modec_ce"], modec_ce.__version__)
        self.assertIn(s["commit"], (None, s["commit"]))
        if s["commit"] is None:
            self.assertIn("AUSENTE", s["procedencia_codigo"])      # P2: ausente no se rellena con un valor
        else:
            self.assertRegex(s["commit"], r"^[0-9a-f]{40}$")
            self.assertIn(s["arbol_limpio"], (True, False))

    def test_registro_minimo_cero_y_false_son_presentes(self):
        R = nucleo.registro_minimo
        self.assertEqual(R({"a": 0}, "a").name, "PRESENTE")
        self.assertEqual(R({"a": False}, "a").name, "PRESENTE")
        self.assertEqual(R({"a": None}, "a").name, "VACIO")
        self.assertEqual(R({"a": " "}, "a").name, "VACIO")
        self.assertEqual(R({}, "a").name, "AUSENTE")
        self.assertEqual(R({"a": {"b": 3}}, "a.b").name, "PRESENTE")
        self.assertEqual(R({"a": {}}, "a.b").name, "AUSENTE")

    @unittest.skipUnless(nucleo.DISPONIBLE, "pesd-nucleo no disponible")
    def test_registro_minimo_coincide_con_p2_del_nucleo(self):
        casos = [{}, {"a": 0}, {"a": 0.0}, {"a": False}, {"a": None}, {"a": ""}, {"a": "  "}, {"a": []},
                 {"a": {}}, {"a": float("nan")}, {"a": 5}, {"a": "x"}, {"a": {"b": 0}}]
        for d in casos:
            for ruta in ("a", "a.b"):
                self.assertEqual(nucleo.registro_minimo(d, ruta).name, nucleo.registro(d, ruta).name, (d, ruta))

    def test_piloto_completo_sin_nucleo_pesd(self):
        """Simula un clon público: proceso aparte con MODEC_CE_SIN_PESD=1 y sin la ruta del núcleo."""
        codigo = "\n".join([
            "import tempfile, json; from pathlib import Path",
            "from modec_ce import nucleo",
            "assert not nucleo.DISPONIBLE",
            "from modec_ce.evidencia import CadenaEvidencia",
            "with tempfile.TemporaryDirectory() as t:",
            "    c = CadenaEvidencia(Path(t) / 'e.jsonl')",
            "    [c.asentar({'i': i}) for i in range(3)]",
            "    v = CadenaEvidencia(Path(t) / 'e.jsonl').verificar()",
            "    print(json.dumps(v))",
        ])
        entorno = {**os.environ, "MODEC_CE_SIN_PESD": "1", "PYTHONPATH": str(RAIZ)}
        entorno.pop("MODEC_CE_PESD_SRC", None)
        salida = subprocess.run([sys.executable, "-B", "-c", codigo], cwd=RAIZ, env=entorno,
                                capture_output=True, text=True, check=True).stdout
        v = json.loads(salida)
        self.assertTrue(v["integra"])
        self.assertEqual(v["registros"], 3)
        self.assertEqual(v["motor_evidencia"], nucleo.FORMATO_MINIMO)


class CompresionC1Tests(unittest.TestCase):
    def test_replica_integrada_coincide_con_instrumento_original(self):
        try:
            original = simulacion.medir_compresion(CFG_PEQUENA, instrumento="modec_core")
        except ImportError:
            self.skipTest("modec_core (MODEC original) no disponible")
        replica = simulacion.medir_compresion(CFG_PEQUENA, instrumento="integrado")
        original.pop("instrumento")
        replica.pop("instrumento")
        self.assertEqual(original, replica)


class CifrasReadmeTests(unittest.TestCase):
    """Las cifras del README deben salir de la simulación actual (evita documentación desincronizada)."""

    def test_readme_cita_las_cifras_de_la_simulacion(self):
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        if "<!-- CIFRAS -->" not in readme:
            self.skipTest("README sin bloque de cifras")
        sim = simulacion.ejecutar()
        ah = sim["ahorro_relativo"]
        esperadas = [f"{ah['modec_vs_ingenua_rol']['peak']:.1%}", f"{ah['modec_compresion_vs_ingenua_rol']['peak']:.1%}",
                     f"{ah['modec_vs_ingenua_volatil']['peak']:.1%}",
                     f"{ah['modec_compresion_vs_ingenua_volatil']['peak']:.1%}",
                     f"{sim['compresion_c1']['compression_savings_ratio']:.1%}",
                     f"{sim['compresion_c1']['preserved_anchor_count']}/{sim['compresion_c1']['required_anchor_count']}"]
        for cifra in esperadas:
            self.assertIn(cifra.replace(".", ","), readme, cifra)


class EvidenciaPublicadaTests(unittest.TestCase):
    """La bitácora publicada del piloto real se verifica sin el núcleo PESD y detecta alteraciones."""

    CARPETA = RAIZ / "evidencia" / "piloto_deepseek_20261121"

    def _verificador(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("verificar_independiente",
                                                      RAIZ / "herramientas" / "verificar_independiente.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _cadena_sintetica(self, carpeta: Path) -> None:
        """Cadena mínima con 2 corridas x 2 brazos, generada con el código del paquete."""
        cadena = nucleo.CadenaMinima(None, "k")
        previo, lineas, corridas = None, [], {}
        for corrida in ("1", "2"):
            costos = {"ingenua_rol": "0.0100", "modec": "0.0040"}
            for brazo, costo in costos.items():
                previo = cadena.sellar({"tipo": "LLAMADA", "corrida": int(corrida), "brazo": brazo,
                                        "costos_usd": {"peak": costo}}, previo)
                lineas.append(previo.a_json())
            corridas[corrida] = {"ahorro_relativo": 0.6}
        (carpeta / "evidencia.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
        (carpeta / "resumen.json").write_text(json.dumps({"corridas": corridas}), encoding="utf-8")

    def test_cadena_sintetica_integra_y_detecta_alteracion(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            self._cadena_sintetica(carpeta)
            v = self._verificador()
            self.assertTrue(v.verificar(carpeta)["integra"], v.verificar(carpeta)["fallos"])
            lineas = (carpeta / "evidencia.jsonl").read_text(encoding="utf-8").splitlines()
            registro = json.loads(lineas[1])
            registro["payload"]["costos_usd"]["peak"] = "0.0001"
            lineas[1] = json.dumps(registro, ensure_ascii=False)
            (carpeta / "evidencia.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
            self.assertFalse(v.verificar(carpeta)["integra"])

    def test_modo_estricto_del_verificador_independiente(self):
        """Un tercero con la clave debe detectar que se quitaron las firmas, no ver 'íntegra'."""
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            clave = bytes(range(32))
            firmada = nucleo.CadenaMinima(clave, "modec-ce")
            plana = nucleo.CadenaMinima(None, "modec-ce")
            previo_f = previo_p = None
            lineas_f, lineas_p = [], []
            for i in range(3):
                carga = {"tipo": "LLAMADA", "corrida": 1, "brazo": "modec", "costos_usd": {"peak": "0.0010"},
                         "i": i}
                previo_f = firmada.sellar(carga, previo_f)
                previo_p = plana.sellar(carga, previo_p)
                lineas_f.append(previo_f.a_json())
                lineas_p.append(previo_p.a_json())
            v = self._verificador()

            (carpeta / "evidencia.jsonl").write_text("\n".join(lineas_f) + "\n", encoding="utf-8")
            self.assertTrue(v.verificar(carpeta, clave)["integra"])
            self.assertFalse(v.verificar(carpeta)["integra"])            # trae firma y no se dio clave
            self.assertFalse(v.verificar(carpeta, bytes(32))["integra"])  # clave equivocada

            (carpeta / "evidencia.jsonl").write_text("\n".join(lineas_p) + "\n", encoding="utf-8")
            self.assertTrue(v.verificar(carpeta)["integra"])              # sin clave: solo integridad
            informe = v.verificar(carpeta, clave)
            self.assertFalse(informe["integra"])
            self.assertTrue(any("sin HMAC" in f for f in informe["fallos"]), informe["fallos"])

    def test_registro_malformado_se_reporta_no_lanza_excepcion(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            c = nucleo.CadenaMinima(None, "modec-ce")
            r = c.sellar({"tipo": "LLAMADA"}, None)          # sin corrida, brazo ni costo
            (carpeta / "evidencia.jsonl").write_text(r.a_json() + "\n", encoding="utf-8")
            informe = self._verificador().verificar(carpeta)
            self.assertFalse(informe["integra"])
            self.assertTrue(any("sin corrida" in f for f in informe["fallos"]), informe["fallos"])

    def test_el_verificador_declara_si_falta_fecha_o_commit_en_el_sello(self):
        if not self.CARPETA.exists():
            self.skipTest("sin bitácora publicada")
        informe = self._verificador().verificar(self.CARPETA)
        if informe["fecha_declarada_utc"] is None:
            self.assertTrue(any("SIN FECHA" in x for x in informe["limites"]), informe["limites"])
        if informe["commit_declarado"] is None:
            self.assertTrue(any("SIN COMMIT" in x for x in informe["limites"]), informe["limites"])

    def test_el_informe_publicado_incluye_la_bitacora_del_repositorio(self):
        """La página que se publica decía «Sin pilotos ejecutados» aunque el repo trae una bitácora
        verificable: contradecía al propio repositorio. El informe debe citarla, con su ruta."""
        if not self.CARPETA.exists():
            self.skipTest("sin bitácora publicada")
        from modec_ce import cli
        pilotos = cli._recoger_pilotos()
        publicadas = [p for p in pilotos if p.get("_publicada")]
        self.assertTrue(publicadas, "ninguna bitácora de evidencia/ llegó al informe")
        self.assertTrue(any(p["_carpeta"].startswith("evidencia/") for p in publicadas))

        pagina = informe.generar_html(simulacion.ejecutar(), pilotos)
        self.assertNotIn("Sin pilotos ejecutados", pagina)
        self.assertIn(publicadas[0]["_carpeta"], pagina)
        self.assertIn("verificar_independiente.py", pagina)
        for dato in (informe.AUTOR, informe.LICENCIA, modec_ce.__version__, informe.REPO):
            self.assertIn(dato, pagina)

    def test_sin_bitacoras_el_informe_no_afirma_que_no_hubo_pilotos(self):
        pagina = informe.generar_html(simulacion.ejecutar(), [])
        self.assertNotIn("Sin pilotos ejecutados", pagina)
        self.assertIn("no significa que no se hayan ejecutado pilotos", pagina)

    def test_bitacora_publicada_integra(self):
        if not self.CARPETA.exists():
            self.skipTest("sin bitácora publicada")
        informe = self._verificador().verificar(self.CARPETA)
        self.assertTrue(informe["integra"], informe["fallos"])
        self.assertEqual(informe["llamadas"], 48)

    def test_alteracion_detectada(self):
        if not self.CARPETA.exists():
            self.skipTest("sin bitácora publicada")
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "ev"
            shutil.copytree(self.CARPETA, copia)
            lineas = (copia / "evidencia.jsonl").read_text(encoding="utf-8").splitlines()
            registro = json.loads(lineas[4])
            registro["payload"]["acierto"] = 99999
            lineas[4] = json.dumps(registro, ensure_ascii=False)
            (copia / "evidencia.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
            self.assertFalse(self._verificador().verificar(copia)["integra"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
