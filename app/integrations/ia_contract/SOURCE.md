# Origen de `ia_contract/`

Copia **sin editar** de los archivos MIT del contrato IA → Back (`LICENSE-CONTRATO-MIT.txt`).

| Archivo | Origen | Commit |
|---|---|---|
| `contract.py` | `ia-clasificacion-fauna/wwm_pipeline/contract.py` | `cdf3292` |
| `enums.py` | `ia-clasificacion-fauna/wwm_pipeline/enums.py` | `cdf3292` |
| `package.py` | `ia-clasificacion-fauna/wwm_pipeline/package.py` | `cdf3292` |
| `formats.py` | `ia-clasificacion-fauna/wwm_pipeline/formats.py` | `cdf3292` |
| `app/data/speciesnet_catalog.json` | `ia-clasificacion-fauna/catalog/speciesnet_catalog.json` (MIT, HU-IA-19) | `cdf3292` |
| `tests/fixtures/package/*.wwm.zip` | `ia-clasificacion-fauna/tests/fixtures/package/` (MIT) | `cdf3292` |
| `LICENSE-CONTRATO-MIT.txt` | `ia-clasificacion-fauna/LICENSE-CONTRATO-MIT.txt` | `cdf3292` |

**No editar a mano.** Para actualizar: volver a copiar desde el repo de la IA, cambiar el commit
en esta tabla y en `EXPECTED_SHA256` de `tests/test_spike01_ai_contract.py`, y avisar a Diego si
cambia `CONTRACT_VERSION`.

**`package_validator.py` todavía no se copia:** hoy es AGPL-3.0 (no figura en `LICENSE-CONTRATO-MIT.txt`). El back lo replica paso a paso en `app/services/package_validator.py` (mismos controles, orden y códigos; paridad verificada sobre los 8 paquetes de prueba y 6 casos extra). Cuando la IA lo publique como MIT, se copia sin editar y se borra la réplica.
