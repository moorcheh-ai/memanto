\## Bug: Pytest asyncio marker not configured



\### Descripción

Los archivos de prueba (`test\_api.py`, `test\_cors\_fix.py`, `test\_e2e.py`) utilizan el marcador `@pytest.mark.asyncio`, pero el plugin `pytest-asyncio` no está configurado correctamente en el proyecto, lo que provoca que las pruebas fallen con el error: `'asyncio' not found in 'markers' configuration option`.



\### Pasos para Reproducir

1\. Clonar el repositorio.

2\. Instalar las dependencias: `pip install -e ".\[all]"`

3\. Ejecutar las pruebas: `pytest tests/ -v`



\### Solución Propuesta

Agregar `pytest-asyncio` a las dependencias de desarrollo y configurarlo en `pyproject.toml` o `pytest.ini` con:



```ini

\[tool.pytest.ini\_options]

asyncio\_mode = "auto"

