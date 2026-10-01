<p align="center">
  <a href="https://www.memanto.ai/">
    <img alt="Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="440">
  </a>
</p>

<h3 align="center">¡La memoria que los agentes de IA adoran!</h3>

<p align="center">
  Memanto es un <strong>Agente de Memoria</strong>, un agente compañero que administra las memorias de tus otros agentes:<br>
  qué conservar, qué entra en conflicto, qué caduca y quién necesita saberlo.
</p>

<p align="center">
  <a href="https://github.com/moorcheh-ai/memanto"><img alt="Estrellas de GitHub" src="https://img.shields.io/github/stars/moorcheh-ai/memanto?style=social"></a>
  <a href="https://pepy.tech/projects/memanto"><img alt="Descargas" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
  <a href="https://arxiv.org/abs/2604.22085"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2604.22085-b31b1b.svg"></a>
  <a href="https://pypi.org/project/memanto/"><img alt="PyPI" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="Licencia MIT" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
</p>

```bash
pip install memanto
```

<!-- ============================================================
     GIF DE DEMOSTRACIÓN — recurso pendiente de mayor impacto. assets/demo.gif
     Cinta VHS proporcionada por separado. Menos de 15 s y de 3 MB.
     ============================================================ -->
<p align="center">
  <img alt="Memanto en 15 segundos" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/demo.gif" width="900">
</p>

---

> **Todas las plataformas guardarán la memoria de tus agentes. Ninguna la administrará.** Gestionarla entre plataformas va contra sus intereses. Ese es el trabajo de un Agente de Memoria.

La persistencia ya está resuelta. Claude, Bedrock, Cursor y cualquier almacén vectorial guardarán lo que escriban tus agentes. Ninguno te avisará de que dos agentes creen ahora cosas opuestas sobre autenticación, que una preferencia antigua ha superado una decisión reciente o que un agente va a repetir trabajo que otro ya terminó y revirtió.

El almacenamiento es un archivador. Memanto es el jefe de gabinete: decide qué entra, vigila el acceso, resuelve contradicciones, descarta lo obsoleto e informa a cada agente antes de que actúe.

---

## Es un agente, no una API

Memanto no es una biblioteca a la que llamas. Es un segundo agente que trabaja junto a tu flota y hace seis cosas según su propio criterio. Cada una es un comportamiento real respaldado por un comando; nada de esto es un elemento de una hoja de ruta.

| | Lo que hace Memanto | Ejecútalo |
|---|---|---|
| **Observa y extrae** | Extrae conocimiento duradero de tráfico efímero — decisiones, preferencias, hechos y fallos — en vez de archivar transcripciones completas. | `memanto remember --from-conversation` |
| **Consolida** | Fusiona memorias en un único patrimonio canónico: los duplicados se colapsan, los fragmentos se unen y las observaciones repetidas refuerzan la confianza. | `memanto schedule enable` |
| **Reconcilia** | El conocimiento nuevo que contradice al anterior lo sustituye, conservando qué se creía y cuándo. | `memanto conflicts` |
| **Olvida** | El deterioro, la caducidad y la eliminación deliberada son políticas que ejecuta; el olvido gestionado mantiene precisa la recuperación. | `memanto forget` |
| **Informa** | Antes de actuar, cada agente recibe la porción mínima relevante del patrimonio; no necesita consultar nada. | `memanto agent bootstrap` |
| **Mueve conocimiento** | Open Knowledge Format permite que una flota entre frameworks y proveedores comparta una memoria en lugar de cinco silos. | `memanto memory export --okf` |

**Y lo hace mientras duermes.** `memanto schedule enable` ejecuta el ciclo diario: selecciona memorias, fusiona duplicados y señala contradicciones para tu revisión.

---

## 60 segundos para una flota gestionada

```bash
pip install memanto
memanto                            # "On-Prem" (Docker, sin cuenta) o "Cloud" (clave gratuita)
memanto connect claude-code        # también: cursor, codex, windsurf, cline, goose, copilot…
```

Tus agentes ahora comparten un patrimonio gestionado. Sin cambios de código, sin wrapper, sin reescribir el ciclo de tus agentes.

```bash
# backend-agent aprende algo el lunes
memanto remember "Auth migrated to JWT — session cookies deprecated" --type decision

# review-agent, que nunca vio esa sesión, lo sabe el viernes
memanto recall "how does auth work"
memanto answer  "why did we drop session cookies?"     # basado en evidencia, sin clave de API adicional

# ¿qué creía la flota el martes pasado? ¿qué cambió desde el lanzamiento?
memanto recall "deployment policy" --as-of 2026-08-05
memanto recall "deployment policy" --changed-since v2.1
```

macOS, Linux, Windows. `memanto ui` abre un panel local sobre todo el patrimonio: explóralo, búscalo y audítalo.

---

## Sé dueño de la memoria de tus agentes

Esta es la parte que importará dentro de dos años, y la que todas las funciones de memoria nativas de las plataformas están diseñadas para impedir.

**Tu patrimonio es un archivo.** `memanto memory export --okf` te da el [Open Knowledge Format](https://docs.memanto.ai/integrations/okf): Markdown plano, legible, comparable con diff, apto para commits y búsquedas con grep. No un volcado propietario: el formato de trabajo real.

**Se mueve.** `memanto migrate` importa desde Mem0, Letta, Supermemory o cualquier paquete OKF, y el mismo comando funciona a la inversa. OKF es un formato abierto que cualquier framework o proveedor puede implementar, incluidos nuestros competidores.

**Se ejecuta en tu máquina.** Docker local + Ollama, sin cuenta, sin clave de API, sin que nada salga de tu infraestructura. O nube gratuita, o tu propio alojamiento. `memanto config backend` cambia entre ellos y el patrimonio viaja contigo.

**MIT.** Sin un nivel open-core esperando para bloquear la mitad útil. Sin flags de funciones, sin límites de asientos, sin retirada de la alfombra.

No hay dependencia porque no hay nada que bloquear.

---

## Seguridad y soberanía

<!-- ============================================================
     TODO — Majid: completa esto con tu trabajo de endurecimiento. La estructura
     es correcta; los detalles son tuyos. Los elementos marcados ⟨…⟩ requieren datos.
     Todo lo que no puedas fundamentar hoy, elimínalo en vez de suavizarlo.
     ============================================================ -->

**Nada sale de tu máquina en modo on-prem.** Docker + Ollama, sin cuenta ni llamadas salientes. Todo el ciclo — extracción, consolidación, reconciliación e informe — se ejecuta localmente.

**Con ámbito definido por defecto.** Cada agente obtiene su propio espacio de nombres; aprovisionas exactamente lo que cada uno debe saber y nada más.

**Cada creencia es rastreable.** Puntuación de confianza, fuente, procedencia y marca de tiempo permiten volver al momento en que una creencia entró en la flota.

**Olvidar es una decisión tuya, no un efecto secundario.** Una memoria está `active` o `expired`, nada más. Solo expira por una política que escribiste y lleva la fecha y la regla. Las expiradas siguen apareciendo claramente etiquetadas; `memanto memory restore` recupera una. Eliminar es distinto y explícito.

---

## Memoria que caduca en tus propios términos

Cada memoria está **activa** hasta que una política la retira. La caducidad queda registrada, es auditable y reversible: el contenido sobrevive y la memoria sigue apareciendo marcada como `[EXPIRED]` con la razón.

```bash
memanto policy list-preset          # conservative / balanced / aggressive
memanto policy apply-preset balanced  # la muestra completa y luego pregunta
memanto policy apply --dry-run      # exactamente qué caducaría, por regla
memanto policy apply                # muestra la política y las coincidencias, luego confirma
```

Las políticas viven en `~/.memanto/policies/<agent>.yaml` y combinan una tabla de retención por tipo con reglas con nombre. Gana la primera regla que coincida, que también puede *fijar* una memoria:

```yaml
retention:
  context: 7d
  event: 30d
  preference: never          # las verdades duraderas del usuario no caducan
rules:
  - name: pinned
    match: {tags: [pinned]}
    expire_after: never      # una fijación explícita prevalece sobre la tabla
  - name: low-confidence-guesses
    match: {provenance: [inferred], confidence_below: 0.5}
    expire_after: 14d
purge_expired_after: never   # eliminación definitiva opcional, desactivada por defecto
```

La recuperación muestra ambos estados; delimita con `--active` o `--expired`. `--as-of` sigue reconstruyendo lo que era verdad entonces, incluso memorias que hayan expirado desde entonces.

```bash
memanto memory expire mem-123       # retira una manualmente
memanto memory restore mem-123      # y la recupera
```

La tarea nocturna (`memanto schedule enable`) ejecuta el barrido. Un agente sin política no caduca nada.

---

## A diferencia del almacenamiento de memoria

| | Almacenamiento de memoria | **Memanto** |
|---|---|---|
| Qué es | Una base de datos con un SDK: escribir, incrustar, recuperar | Un agente con criterio sobre la memoria de tu flota |
| Comportamiento principal | Persistir | Seleccionar, reconciliar, consolidar, olvidar, informar |
| Quién decide qué se conserva | Tú, en el código de la aplicación | Memanto, según una política que configuras una vez |
| Cuando dos agentes discrepan | Gana silenciosamente la última escritura | Ambos quedan versionados y se presentan para revisión |
| Olvido | Un `DELETE` que debes recordar ejecutar | Una política de primera clase que se ejecuta según programación |
| Ámbito | Una aplicación, un stack, las paredes de un proveedor | Una flota, entre stacks y proveedores |
| Tus datos | Exportables en teoría | El formato de trabajo *es* Markdown portátil |

Los sustratos de almacenamiento están *debajo* de Memanto: almacenes vectoriales, sistemas de archivos y memorias nativas de plataformas son backends que administra.

---

<p align="center">
  <strong>⭐ Marca el repositorio con una estrella si Memanto administra la memoria de tu flota</strong><br>
  <sub>Es la señal que nos dice que sigamos construyendo esto en abierto, bajo MIT, sin reservarnos nada.</sub></p>

---

## Experiencia de desarrollo

**Un solo `pip install`.** Sin almacén vectorial, canalización de embeddings, reranker, migración de esquema ni backend que cuidar. El motor de recuperación viene incluido.

**Funciona con lo que ya ejecutas.** `memanto connect claude-code`; lo mismo para Cursor, Codex, Windsurf, Cline, Continue, Goose, Copilot y más.

**Se puede buscar en cuanto se escribe.** Sin extracción al escribir, grafo que reconstruir ni cola de indexación. `remember` devuelve y todos los agentes ya pueden recuperarla.

**Tipado, no una sopa.** 13 categorías: `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship` y más; la recuperación se puede filtrar.

**Un panel, no un archivo de registro.** `memanto ui` para todo el patrimonio, `memanto daily-summary` para un resumen y `memanto status` para agentes, sesiones y estado.

---

<details>
<summary><strong>Referencia completa de CLI</strong></summary>

<br>

| Funcionalidad | Comandos | Qué hace |
|---|---|---|
| Estado del sistema | `memanto status` | Entorno, configuración, salud del servidor, sesión activa y agentes registrados. |
| API REST local + interfaz web | `memanto serve`, `memanto ui` | Ejecuta la API REST localmente y abre una interfaz de navegador. |
| Ciclo de vida del agente | `memanto agent ...` | Crea, enumera o elimina agentes, activa sesiones y ejecuta `agent bootstrap`. |
| Captura de memoria a escala | `memanto remember` | Memorias individuales, JSON por lotes o `--from-conversation`. |
| Edición y eliminación | `memanto edit`, `memanto forget` | Actualiza una memoria o elimina una incorrecta. |
| Ingesta de archivos | `memanto upload` | Incorpora .pdf, .docx, .xlsx, .json, .txt, .csv y .md al espacio de nombres de un agente. |
| Recuperación avanzada | `memanto recall` | Búsqueda y consultas temporales (`--as-of`, `--changed-since`) con filtros. |
| Respuestas fundamentadas | `memanto answer` | Genera respuestas a partir de memoria recuperada. |
| Inteligencia diaria | `memanto daily-summary`, `memanto conflicts` | Resúmenes, contradicciones y resolución interactiva. |
| Sesiones y automatización | `memanto session ...`, `memanto schedule ...` | Inspecciona sesiones y habilita ejecuciones diarias. |
| Exportación y sincronización | `memanto memory export`, `memanto memory sync` | Exporta Markdown y sincroniza `MEMORY.md`; `--okf` crea un paquete [OKF](https://docs.memanto.ai/integrations/okf). |
| Importación y migración | `memanto migrate` | Importa desde Mem0, Letta, Supermemory o OKF. |
| Configuración | `memanto config show` | Estado de clave API, agente/sesión activa, servidor y horario. |
| Integración de la flota | `memanto connect ...` | Claude Code, Codex, Cursor, Windsurf, Antigravity, Gemini CLI, Cline, Continue, OpenCode, Goose, Roo, GitHub Copilot, Augment. |

**Tipos de memoria:** `instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

```bash
memanto remember "User prefers concise answers" --type preference
memanto recall "user communication style" --type preference
```

Referencia completa: [Guía de usuario de la CLI](https://docs.memanto.ai/cli)

</details>

<details>
<summary><strong>Opciones de instalación: completamente local frente a nube gratuita</strong></summary>

<br>

**Completamente local. Sin cuenta, sin clave de API; nada sale de tu máquina:**

```bash
pip install memanto
memanto           # elige "On-Prem"; guía la configuración de Docker + Ollama
```

Requiere Docker.

**Nube gratuita. Sin tarjeta, ~60 segundos:**

```bash
pip install memanto
memanto           # elige "Cloud"; pega tu clave de API gratuita
```

Clave gratuita en [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys): 100K operaciones gratuitas.

Cambia cuando quieras: `memanto config backend`

</details>

<details>
<summary><strong>Arquitectura</strong></summary>

<br>

La recuperación usa un motor semántico de teoría de la información incluido, como contenedor Docker local o servicio de nube gratuito. La CLI `memanto` gestiona ambos; los sustratos de almacenamiento son intercambiables y Memanto es el agente que está por encima.

<p align="center">
  <img alt="Arquitectura" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="900">
</p>

**On-prem:**

<p align="center">
  <img alt="Arquitectura on-prem" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="900">
</p>

</details>

<details>
<summary><strong>SDK y API REST</strong></summary>

<br>

**TypeScript / Node.js**: [`@moorcheh-ai/memanto`](../sdks/typescript) inicia un servidor local de Memanto mediante `uvx` y expone un cliente ergonómico (`remember` / `recall` / `answer`).

**API REST**: inicia con `memanto serve`. Referencia en [docs.memanto.ai/api](https://docs.memanto.ai/api) y `http://localhost:8000/docs` mientras se ejecuta.

</details>

---

## Véalo en acción

| | |
|---|---|
| [**Recuperar es más que buscar**](https://youtu.be/zoKP4b_rUhY) — 6:20 | [**Configuración y demostración**](https://www.youtube.com/watch?v=vEtOaoweIG4) |
| [**Recorrido por el panel local**](https://www.youtube.com/watch?v=5n976CmzohE) | [**Documentación →**](https://docs.memanto.ai) |

---

## Investigación

**[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://arxiv.org/abs/2604.22085)**

En benchmarks públicos de recuperación informamos 89.8% en LongMemEval y 87.1% en LoCoMo. <!-- TODO: indica aquí el modelo lector, el modelo juez y el subconjunto; deberías hacer legibles las condiciones. --> Los conjuntos de datos y el arnés están abiertos en [huggingface.co/moorcheh](https://huggingface.co/moorcheh): ejecútalos tú mismo.

Una salvedad: las puntuaciones entre proyectos no son comparables. El modelo lector, el modelo juez, el prompt del juez y el presupuesto de recuperación cambian los resultados varios puntos y las ejecuciones publicadas no comparten configuración. Considera cualquier cifra, incluida la nuestra, como orientativa. Un Agente de Memoria debería medirse por la calidad del patrimonio con el tiempo: contradicciones, obsolescencia y precisión en el mes seis.

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026},
      eprint={2604.22085},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---

## Comunidad

<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Reddit"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Documentación"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/27378"><img src="https://trendshift.io/api/badge/repositories/27378" alt="Trendshift" width="220"></a>
  <!-- <a href="https://mcptoplist.com/server/glama%2Fmoorcheh-ai%2Fmemanto"><img src="https://mcptoplist.com/badge/glama%2Fmoorcheh-ai%2Fmemanto.svg" alt="MCP Top List" width="220"></a> -->
  <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
</p>

Preguntas: [support@moorcheh.ai](mailto:support@moorcheh.ai) · [@moorcheh_ai](https://x.com/moorcheh_ai)

---

<p align="center">
  <strong>Licencia MIT</strong><br>
  <sub><a href="../README.md">English</a> · <a href="README_es.md">Español</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_ja.md">日本語</a></sub>
</p>
