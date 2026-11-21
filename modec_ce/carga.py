"""
Carga de trabajo multiagente MODEC y disposiciones de prompt.

Un ciclo MODEC tiene T pasos; en cada paso actúa un orquestador y N agentes-partícula.
Cada petición se compone de los mismos segmentos en todas las disposiciones; solo
cambia el orden. Así la comparación aísla el efecto del caché de prefijos:

  FUNDACION  prefijo invariante del sistema (GlobalSystemFoundation de MODEC)
  CONTEXTO   corpus compartido por todos los agentes
  HISTORIAL  salidas de pasos anteriores (completas o como Super-Tokens)
  ROL        instrucciones del agente
  TAREA      directiva del paso
  VOLATIL    metadatos que cambian en cada petición (marca de tiempo, id)

El contenido es sintético y determinista (semilla), sin datos privados ni externos.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Sequence

CLASES = ("FUNDACION", "CONTEXTO", "HISTORIAL", "ROL", "TAREA", "VOLATIL")

DISPOSICIONES: dict[str, tuple[str, ...]] = {
    # Patrón frecuente: metadatos de la petición arriba del todo.
    "ingenua_volatil": ("VOLATIL", "FUNDACION", "ROL", "TAREA", "CONTEXTO", "HISTORIAL"),
    # Patrón frecuente: cada agente empieza por su rol; sin metadatos al inicio.
    "ingenua_rol": ("ROL", "FUNDACION", "CONTEXTO", "TAREA", "HISTORIAL", "VOLATIL"),
    # MODEC-CE: de lo más estable a lo más variable.
    "modec": ("FUNDACION", "CONTEXTO", "HISTORIAL", "ROL", "TAREA", "VOLATIL"),
}

LIMITE_RESUMEN_SUPERTOKEN = 350          # mismo límite que el encoder MODEC v2.6
_ANCLA = re.compile(r"\[H-\d{3}\]")


@dataclass(frozen=True)
class Segmento:
    clase: str
    texto: str


@dataclass(frozen=True)
class Peticion:
    disposicion: str
    paso: int
    agente: str
    segmentos: tuple[Segmento, ...]

    @property
    def texto(self) -> str:
        return "\n\n".join(s.texto for s in self.segmentos)

    @property
    def huella_contenido(self) -> str:
        """Huella del conjunto de segmentos sin importar el orden (para probar que el contenido es el mismo)."""
        partes = sorted(f"{s.clase}\x00{s.texto}" for s in self.segmentos)
        return hashlib.sha256("\x01".join(partes).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConfigCarga:
    semilla: int = 2026
    pasos: int = 3
    agentes: tuple[str, ...] = ("analista", "auditor", "redactor", "verificador")
    tokens_corpus: int = 4000
    tokens_salida_agente: int = 600
    secciones_corpus: int = 12

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SuperToken:
    agente: str
    paso: int
    uri: str
    resumen: str
    anclas: tuple[str, ...]

    def texto(self) -> str:
        return (f"ST|{self.agente}|t{self.paso}|{self.uri}|anclas={','.join(self.anclas)}|"
                f"{self.resumen}")


def supertoken(agente: str, paso: int, salida: str) -> SuperToken:
    """Comprime una salida a un Super-Token: referencia SHA-256 + resumen acotado + anclas citadas."""
    uri = "artifact://sha256:" + hashlib.sha256(salida.encode("utf-8")).hexdigest()
    anclas = tuple(dict.fromkeys(_ANCLA.findall(salida)))
    return SuperToken(agente, paso, uri, salida[:LIMITE_RESUMEN_SUPERTOKEN], anclas)


# ---------------------------------------------------------------- contenido sintético

_VOCAB = ("registro", "evidencia", "contrato", "perfil", "campo", "sello", "cadena", "ventana", "umbral",
          "trayectoria", "versión", "integridad", "presencia", "fidelidad", "madurez", "auditoría", "cobertura",
          "intento", "directiva", "cierre", "consistencia", "dependencia", "riesgo", "latencia", "reintento")


def _frase(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(_VOCAB) for _ in range(n)).capitalize() + "."


def generar_corpus(cfg: ConfigCarga) -> str:
    rng = random.Random(cfg.semilla)
    por_seccion = max(1, cfg.tokens_corpus // cfg.secciones_corpus)
    partes = ["CORPUS COMPARTIDO — especificación técnica sintética (sin datos reales)."]
    ancla = 0
    for s in range(1, cfg.secciones_corpus + 1):
        partes.append(f"## Sección {s}")
        escritos = 0
        while escritos < por_seccion:
            ancla += 1
            frase = f"[H-{ancla:03d}] " + _frase(rng, 12)
            partes.append(frase)
            escritos += 16
    return "\n".join(partes)


def salida_sintetica(cfg: ConfigCarga, agente: str, paso: int) -> str:
    rng = random.Random(f"{cfg.semilla}-{agente}-{paso}")
    lineas = [f"Informe de {agente}, paso {paso}."]
    escritos = 0
    while escritos < cfg.tokens_salida_agente:
        lineas.append(f"Hallazgo sobre [H-{rng.randint(1, 3 * cfg.secciones_corpus):03d}]: " + _frase(rng, 10))
        escritos += 16
    return "\n".join(lineas)


FUNDACION = ("FUNDACIÓN DEL SISTEMA MODEC. Eres un agente de un ciclo multiagente. Responde en español, en "
             "texto breve y verificable. Cita las anclas [H-nnn] del corpus que uses. No inventes datos. "
             "Formato de salida: viñetas.")


def rol_de(agente: str) -> str:
    return f"ROL: {agente}. Aplica tu especialidad ({agente}) al corpus y al historial."


def tarea_de(agente: str, paso: int) -> str:
    return f"TAREA paso {paso}: como {agente}, identifica dos hallazgos nuevos y una inconsistencia."


def volatil_de(id_peticion: str, marca: str) -> str:
    return f"METADATOS: petición {id_peticion} · {marca}"


# ------------------------------------------------------------------ construcción

def componer(disposicion: str, paso: int, agente: str, piezas: dict[str, str]) -> Peticion:
    if disposicion not in DISPOSICIONES:
        raise ValueError(f"disposición desconocida: {disposicion}")
    faltan = set(CLASES) - set(piezas)
    if faltan:
        raise ValueError(f"faltan segmentos: {sorted(faltan)}")
    segs = tuple(Segmento(c, piezas[c]) for c in DISPOSICIONES[disposicion])
    return Peticion(disposicion, paso, agente, segs)


def texto_historial(entradas: Sequence[tuple[str, int, str]], comprimir: bool) -> str:
    """Historial append-only en orden (paso, agente). Comprimido = Super-Tokens."""
    if not entradas:
        return "HISTORIAL: (vacío)"
    if comprimir:
        return "HISTORIAL (Super-Tokens):\n" + "\n".join(supertoken(a, p, s).texto() for a, p, s in entradas)
    return "HISTORIAL:\n" + "\n\n".join(f"<<{a} t{p}>>\n{s}" for a, p, s in entradas)


def plan_ciclo(cfg: ConfigCarga) -> list[tuple[int, str]]:
    """Secuencia de actores: en cada paso, el orquestador y luego los agentes."""
    return [(p, a) for p in range(1, cfg.pasos + 1) for a in ("orquestador", *cfg.agentes)]


def generar_peticiones(
    cfg: ConfigCarga,
    disposicion: str,
    *,
    comprimir_historial: bool,
    salida_de: Callable[[str, int], str] | None = None,
    volatil: Callable[[int], tuple[str, str]] | None = None,
) -> list[Peticion]:
    """Genera las peticiones del ciclo. `salida_de` permite usar salidas reales del modelo."""
    corpus = generar_corpus(cfg)
    salida_de = salida_de or (lambda a, p: salida_sintetica(cfg, a, p))
    volatil = volatil or (lambda i: (f"REQ-{i:05d}", f"2026-11-20T00:{i // 60:02d}:{i % 60:02d}Z"))
    historial: list[tuple[str, int, str]] = []
    peticiones: list[Peticion] = []
    paso_actual = 1
    pendientes: list[tuple[str, int, str]] = []
    for i, (paso, agente) in enumerate(plan_ciclo(cfg)):
        if paso != paso_actual:                      # el historial se actualiza al cerrar cada paso
            historial.extend(pendientes)
            pendientes = []
            paso_actual = paso
        id_peticion, marca = volatil(i)
        piezas = {
            "FUNDACION": FUNDACION,
            "CONTEXTO": corpus,
            "HISTORIAL": texto_historial(historial, comprimir_historial),
            "ROL": rol_de(agente),
            "TAREA": tarea_de(agente, paso),
            "VOLATIL": volatil_de(id_peticion, marca),
        }
        peticiones.append(componer(disposicion, paso, agente, piezas))
        pendientes.append((agente, paso, salida_de(agente, paso)))
    return peticiones


def anclas_de(texto: str) -> list[str]:
    return list(dict.fromkeys(_ANCLA.findall(texto)))


def resumen_json(peticiones: Iterable[Peticion]) -> str:
    return json.dumps([{"paso": p.paso, "agente": p.agente, "clases": [s.clase for s in p.segmentos]}
                       for p in peticiones], ensure_ascii=False)
