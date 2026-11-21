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

from modec_ce import nucleo, simulacion, tokens  # noqa: E402
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
