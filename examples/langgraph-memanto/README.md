# LangGraph + Memanto: Memoria Persistente

Ejemplo de un agente LangGraph que recuerda información entre sesiones usando Memanto.

## Setup
```bash
pip install -r requirements.txt
export MOORCHEH_API_KEY=tu_api_key
python agent.py
```

## Cómo funciona
1. `remember_node`: guarda mensajes del usuario en Memanto
2. `recall_node`: recupera memorias relevantes antes de responder
