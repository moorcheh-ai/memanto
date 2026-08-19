<p align="center"><a href="https://www.memanto.ai/"><img alt="Logotipo de MEMANTO" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="500"></a></p>

<div align="center"><h1>La memoria que los agentes de IA adoran</h1></div>
<h2 align="center"><em>Memanto es un agente de memoria complementario: gestiona las memorias de tus otros agentes. Conserva lo que vale la pena guardar, lo consolida entre sesiones e informa a tus agentes cuando empiezan, mientras mantienes la propiedad de todo lo que aprenden.</em></h2>

<p align="center">Funciona autom&aacute;ticamente con Claude Code, Cursor, Codex y m&aacute;s de 20 agentes. Es completamente convertible entre un backend sem&aacute;ntico y Open Knowledge Format (archivos *.md con estilo de wiki para LLM), por lo que puedes inspeccionar, exportar y migrar tu patrimonio de memoria a cualquier lugar: ejecuta <code>memanto migrate</code> y se mueve contigo.</p>
<p align="center"><code>pip install memanto</code></p>

<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Unirse a Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Unirse a Reddit"></a>
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4"><img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Video de configuraci&oacute;n"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Documentaci&oacute;n"></a>
</p>

---
## Qu&eacute; es MEMANTO?

**MEMANTO es un agente de memoria. Recuerda, recupera y responde, para que tus agentes alcancen objetivos a largo plazo y eviten confusiones.**

La mayoria de las herramientas de memoria son infraestructura pasiva: los agentes deben consultarlas, analizar los resultados y decidir que hacer despues. MEMANTO se construyo de otra manera. Es un agente de memoria activo, disenado a partir de las carencias que los propios agentes identificaron al hablar de su memoria: tres operaciones (`remember`, `recall`, `answer`) que dan contexto persistente entre sesiones, con recuperacion de ultima generacion y sin latencia de ingesta.

<div align="center">
  <h1>Memanto en accion</h1>
  <h2>Sin Memanto</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Before.gif" alt="Antes" width="1100" style="border-radius: 8px;">
  <h2>Con Memanto conectado</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/After.gif" alt="Despues" width="1100" style="border-radius: 8px;">
</div>

## Empieza en 2 minutos

Funciona en macOS, Linux y Windows.

**Opcion A: completamente local (sin cuenta ni clave de API):**
```bash
pip install memanto
memanto           # elige "On-Prem"; te guia con Docker + Ollama
```
Requiere Docker. Todo se ejecuta y permanece en tu maquina.

**Opcion B: nube gratuita (sin tarjeta, ~60 segundos):**
```bash
pip install memanto
memanto           # elige "Cloud"; pega tu clave de API gratuita de Moorcheh
```
Obten tu API gratuita en: https://console.moorcheh.ai/api-keys

Puedes cambiar entre local y nube en cualquier momento con `memanto config backend`.

---
## Lo que obtienes

- **No vuelvas a explicar tu base de codigo** despues de cada reinicio de contexto. Memanto persiste entre sesiones y tu agente retoma donde se quedo.
- **Menos tokens consumidos por contexto repetido.** Las memorias solo se recuperan cuando son relevantes.
- **Memorias consultables al instante de guardarse.** Sin espera de indexacion ni coste de extraccion con LLM al escribir.
- **Un solo `pip install`.** Sin base de datos vectorial, esquema, rerankers ni servicio de backend que cuidar.
- **Despliegue flexible.** Ejecuta el backend localmente, usalo como SaaS, alojalo en tu VPC o cambia entre estas opciones cuando quieras.

---
## Integraciones

Funciona con Claude Code, Cursor, Codex, Windsurf, Cline, Continue, Goose, GitHub Copilot y mas. Consulta la [lista completa →](https://docs.memanto.ai/integrations/overview)

```bash
memanto connect <integration-tool-id> # integra con un comando
#ej.: memanto connect claude-code
```

---
## Las seis carencias

| # | Carencia | Que hace MEMANTO al respecto |
| --- | --- | --- |
| 1 | **Inyeccion estatica**: la memoria llega como un bloque, no se puede consultar por relevancia | Consultable, no inyectable |
| 2 | **Sin degradacion temporal**: una preferencia antigua pesa igual que el plazo de ayer | Versionado, senales de actualidad y consultas temporales |
| 3 | **Sin procedencia**: no se distinguen hechos explicitos de patrones inferidos o informacion desactualizada | Metadatos de confianza y procedencia en cada memoria |
| 4 | **Memoria plana**: episodica, semantica y procedimental se mezclan en una capa | Tipada y jerarquica: 13 categorias integradas |
| 5 | **Sin retroescritura**: las contradicciones coexisten en silencio | Deteccion de conflictos, versionado explicito y sin sobrescrituras silenciosas |
| 6 | **Retraso de indexacion**: extraccion obligatoria de LLM y construccion de grafo | Ingesta sin sobrecarga, disponible al escribir |

> *"Mi memoria existe como una instantanea estatica inyectada en el contexto: util, pero fundamentalmente pasiva."* Una cita de un modelo que se convirtio en el briefing de diseno de Memanto.

---
## Benchmarks

- **89.8% en LongMemEval** y **87.1% en LoCoMo**: supera a Mem0, Zep y Letta. [Conjuntos de datos publicos →](https://huggingface.co/moorcheh)
- **Tres primitivas, no dos**: `remember`, `recall` y `answer`; respuestas de LLM basadas en memoria, sin otra clave de API.
- **Recuperacion con una sola consulta.** Sin canalizaciones multietapa, esquema de grafo ni rerankers.
- **Memoria semantica tipada.** 13 categorias: `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship` y mas.

---
## Arquitectura

La recuperacion de Memanto funciona con [Moorcheh](https://moorcheh.ai), un motor sem&aacute;ntico de teoria de la informacion. Se ejecuta como contenedor Docker local (gratis y sin cuenta) o como servicio en la nube gratuito (100 000 operaciones); el CLI `memanto` gestiona ambos por ti.

<p align="center"><img alt="Arquitectura de MEMANTO" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="1000"></p>

### On-Prem
<p align="center"><img alt="Arquitectura on-prem de MEMANTO" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="1000"></p>

---
## Por que Moorcheh?

Moorcheh es el motor sem&aacute;ntico de la recuperacion de Memanto. A diferencia de las bases de datos vectoriales que dependen de busqueda aproximada y requieren canalizaciones de indexacion, Moorcheh usa un enfoque de teoria de la informacion que devuelve resultados exactos sin retraso de indexacion: escribe una memoria y podras buscarla inmediatamente.

Memanto no necesita una base de datos vectorial separada, canalizacion de embeddings ni etapa de reranking. El motor Moorcheh se ejecuta como contenedor Docker local para usuarios on-prem (sin cuenta) o como servicio gestionado en la nube con nivel gratuito. En ambos casos es invisible: el CLI `memanto` lo gestiona.

---
## Configuracion y demo

<p align="center"><a href="https://www.youtube.com/watch?v=vEtOaoweIG4"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-demo.png" alt="Video de configuraci&oacute;n"></a></p>

## Panel local para la mejor experiencia

<p align="center"><a href="https://www.youtube.com/watch?v=5n976CmzohE"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-uidashboard.png" alt="Demo del panel local"></a></p>

---
## Referencia de CLI

| Capacidad | Comandos | Que hace |
|---|---|---|
| Panel de estado del sistema | `memanto status` | Ve entorno, configuraci&oacute;n, salud del servidor, sesion activa y agentes registrados. |
| API REST local e interfaz web | `memanto serve`, `memanto ui` | Ejecuta la API REST de MEMANTO localmente y abre una interfaz interactiva. Opcional para usar el CLI. |
| Gestion de agentes | `memanto agent ...` | Crea, lista o elimina agentes, activa o desactiva sesiones y ejecuta `agent bootstrap`. |
| Captura de memoria | `memanto remember` | Guarda memorias, ingesta lotes JSON o usa `--from-conversation` para extraer hechos de chats. |
| Edicion y eliminacion | `memanto edit`, `memanto forget` | Actualiza una memoria existente o elimina permanentemente una memoria incorrecta u obsoleta. |
| Carga de archivos | `memanto upload` | Sube .pdf, .docx, .xlsx, .json, .txt, .csv o .md al espacio de memoria de un agente; se puede buscar al instante con `recall`. |
| Recuperacion avanzada | `memanto recall` | Ejecuta busqueda estandar y consultas temporales (`--as-of`, `--changed-since`) con filtros. |
| Preguntas y respuestas | `memanto answer` | Genera respuestas RAG usando contexto de memoria recuperado. |
| Flujos diarios | `memanto daily-summary`, `memanto conflicts` | Genera resumenes, detecta contradicciones y resuelve conflictos interactivamente. |
| Sesiones y automatizacion | `memanto session ...`, `memanto schedule ...` | Inspecciona sesiones y habilita resumenes diarios programados. |
| Archivos de memoria | `memanto memory export`, `memanto memory sync` | Exporta Markdown estructurado y sincroniza `MEMORY.md`. Agrega `--okf` para un paquete [Open Knowledge Format](https://docs.memanto.ai/integrations/okf). |
| Importacion y migracion | `memanto migrate` | Importa memorias de Mem0, Letta, Supermemory o un paquete [OKF](https://docs.memanto.ai/integrations/okf). |
| Configuracion | `memanto config show` | Inspecciona claves de API, agente y sesion activos, servidor y hora programada. |
| Integraciones multiagente | `memanto connect ...` | Conecta, elimina o lista integraciones para Claude Code, Codex, Cursor, Windsurf, Antigravity, Gemini CLI, Cline, Continue, OpenCode, Goose, Roo, GitHub Copilot y Augment. |

Para la referencia completa, consulta la [Guia de usuario del CLI](https://docs.memanto.ai/cli).

### Tipos de memoria compatibles

`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

- Guarda con un tipo: `memanto remember "El usuario prefiere respuestas concisas" --type preference`
- Filtra por tipo: `memanto recall "estilo de comunicacion del usuario" --type preference`

---
## SDKs

- **TypeScript / Node.js**: [`@moorcheh-ai/memanto`](../sdks/typescript): inicia un servidor Memanto local mediante `uvx` y expone un cliente `Memanto` ergonomico (`remember` / `recall` / `answer`).

---
## API REST

Memanto expone una API REST basada en sesiones. Inicia el servidor localmente:
```bash
memanto serve
```
La referencia completa esta en [docs.memanto.ai/api](https://docs.memanto.ai/api) y en `http://localhost:8000/docs` cuando el servidor se ejecuta.

---
## Investigacion

[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://huggingface.co/papers/2604.22085)

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026}, eprint={2604.22085}, archivePrefix={arXiv}, primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---
## Soporte

Preguntas o comentarios? Estamos para ayudarte:
- **Documentaci&oacute;n**: [https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**: [Unete a nuestro servidor](https://memanto.ai/discord)
- **Reddit**: [Unete a nuestra comunidad](https://www.reddit.com/r/Memanto/)
- **Correo**: support@moorcheh.ai
- **X / Twitter**: [@moorcheh_ai](https://x.com/moorcheh_ai)

---
**Licencia MIT**

<br>
<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_zh-CN.md">简体中文</a> | <a href="README_ja.md">日本語</a>
</p>