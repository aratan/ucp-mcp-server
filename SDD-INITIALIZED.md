# SDD (Spec-Driven Development) Initialization

## Proyecto Inicializado: ucp-mcp-server

**Fecha**: 2026-07-22  
**Modo**: Hybrid (archivos + Engram memoria persistente)

### Stack Tecnológico Detectado

| Componente | Valor |
|-----------|-------|
| Lenguaje | Python 3.10+ |
| Dependency Manager | hatch, pip, uv |
| Test Runner | pytest 8.x |
| Async Mode | auto (pytest-asyncio) |
| Linter | ruff 0.4+ |
| Formatter | ruff format (double quotes, spaces) |
| Coverage Tool | pytest-cov (disponible pero no instalado) |

### Capabilities de Testing

```markdown
**Strict TDD Mode**: enabled (pyproject.toml + pytest config)

### Test Runner
- Command: `pytest -v`
- Framework: pytest 8.x with pytest-asyncio
- Async mode: auto
- Coverage command: `pytest --cov`

### Test Layers
| Layer       | Available | Tool        |
| ----------- | --------- | ----------- |
| Unit        | ✅        | pytest      |
| Integration | ✅        | respx (HTTP mocking) |
| E2E         | ❌        | —           |

### Coverage
- Available: ✅ (via pytest-cov, must be added to dependencies)
- Command: `pytest --cov=./`

### Quality Tools
| Tool         | Available | Command          |
| -------------| --------- | ---------------- |
| Linter       | ✅        | `ruff check .`   |
| Type checker | ❌        | —                |
| Formatter    | ✅        | `ruff format`    |

### Testing Practices Observed
- Integration tests use respx for HTTP mocking
- Tests separated by domain: discovery, checkout, errors
- Async support via pytest-asyncio with auto mode
- Test markers present but not heavily used yet (e.g., integration marker)
```

### Archivo Creación Inicial

**Archivos creados**:
1. `openspec/config.yaml` - Configuración SDD con estricto TDD habilitado, configuración del proyecto y capacidades de testing.
2. `.atl/skill-registry.md` - Registro completo deSkills disponibles en el entorno (50+ skills).

**Observaciones Engram persistidas**:
1. `sdd-init: proyecto ucp-mcp-server` (ID: 347)
2. `sdd/ucp-mcp-server/testing-capabilities` (ID: 348)

### Siguientes Pasos Recomendados

1. **Explorar el códigobase**: `/sdd-explore "dominio de aplicación"`
2. **Crear cambio inicial**: `/sdd-init` ahora completo, listo para cambios guiados por especificación.

---

*Este proyecto está preparado para desarrollo guiado por especificaciones (SDD). Consulte las convenciones en AGENTS.md.*
