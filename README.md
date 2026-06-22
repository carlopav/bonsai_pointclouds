# Bonsai Point Clouds Extension

Integrazione tra **Bonsai** (IFC models in Blender) e **Point Cloud Visualizer v3** (Jakub Uhlík).

Carica nuvole di punti referenziate nell'IFC e gestisce clip box di clipping in Blender.

## Caratteristiche

- ✅ Pannello collapsibile in Bonsai sezione "Drawings & Documents"
- ✅ Caricamento pointcloud tramite PCV (PLY, LAS, E57)
- ✅ Gestione clip box (IfcAnnotation) per il clipping
- ✅ Supporto multi-versione IFC (2x3, 4, 4x1, 4x2, 4x3)
- ✅ Undo/Redo tramite transazioni Bonsai
- ✅ Dati persistenti nell'IFC (non sesionali)

## Requisiti

- Blender 4.0+
- Bonsai addon
- Point Cloud Visualizer (v3+) — **opzionale** (vedi sotto)

## Backend di visualizzazione

L'addon usa due backend, scelti automaticamente:

| | Con **Point Cloud Visualizer** installato | Senza PCV (viewer integrato) |
|---|---|---|
| Formati | PLY, LAS, LAZ, E57 | **solo PLY** |
| Resa/performance | shader GPU completo, nuvole grandi | viewer GPU minimale (preview) |
| **Clipping** (clip box) | ✅ | ❌ non disponibile |
| Colori per-punto | ✅ | solo se il PLY contiene i colori |

Il viewer integrato è una soluzione di ripiego pensata per non lasciarti senza nulla quando PCV non c'è. **Per l'esperienza completa è fortemente consigliato Point Cloud Visualizer.**

## ⭐ Consigliato: Point Cloud Visualizer (Jakub Uhlík)

Questo addon **non include e non sostituisce** Point Cloud Visualizer: lo pilota soltanto, se presente, tramite le sue API pubbliche. PCV è un prodotto eccellente sviluppato e mantenuto da **Jakub Uhlík** — se lo usi nel tuo lavoro, supporta l'autore acquistando la versione ufficiale:

➡️ **[Point Cloud Visualizer su Blender Market](https://blendermarket.com/products/point-cloud-visualizer)**

Acquistandolo ottieni tutti i formati, le performance su nuvole massive e il clipping, e sostieni lo sviluppo continuo dello strumento.

## Installazione

1. Clona il repo in una cartella Blender:
   ```bash
   cd ~/.config/blender/4.1/scripts/addons/
   git clone https://github.com/carlopav/bonsai_pointclouds.git
   ```

2. Riavvia Blender e abilita l'addon in Edit > Preferences > Add-ons

3. Il pannello **Point Clouds** appare in Properties > Scene > **Drawings and Documents**

## Architettura del modulo

Segue il pattern dei moduli Bonsai (separazione core/tool/data):

```
bonsai_pointclouds/
├── __init__.py    # bl_info, registrazione classi + props + handler refresh
├── const.py       # naming, schema IFC, costanti PCV
├── prop.py        # PropertyGroup (PointCloud, BIMPointCloudProperties)
├── data.py        # PointCloudsData (cache letta dall'IFC per l'UI)
├── tool.py        # PointCloud (implementazione: IFC via ifcopenshell.api, PCV, Blender)
├── core.py        # logica pura (no bpy), orchestrazione tool
├── operator.py    # operatori thin; quelli IFC usano tool.Ifc.Operator (_execute)
└── ui.py          # BIM_PT_point_clouds (figlio di BIM_PT_tab_drawings) + BIM_UL_point_clouds
```

## Uso

1. Nel pannello clicca l'icona **import** per caricare le nuvole referenziate, poi **+** per aggiungerne una (file dialog PLY/LAS/LAZ/E57).
2. Nella lista, per ogni nuvola: **carica nel viewport** (PCV), **visibilità**, **crea clip box**, **abilita/disabilita clipping**, **rimuovi**.

## Architettura Dati (PERSISTENTE nell'IFC)

Ogni nuvola usa **solo entità IFC standard** (nessun pset custom):
- **IfcAnnotation** (`ObjectType = "PointCloud"`) — segnaposto con `IfcObjectPlacement` (posizione persistente, nome `Pointcloud/...` per l'oggetto Blender).
- **IfcDocumentReference** (via `IfcRelAssociatesDocument`) — path del file in `Location`; nome `POINTCLOUD_...`.
- **IfcDocumentInformation.CreationTime** — data di import.

Stato di sessione (NON persistito): visibilità (PCV erase/draw) e clipping (clip box è un cube 3 m solo in Blender).

Scrittura sempre tramite `ifcopenshell.api` (`root.create_entity`, `document.add_information`/`add_reference`/`assign_document`, `geometry.edit_object_placement`), così ownership history e undo/redo sono gestiti da Bonsai.

## Note Tecniche

- Le mutazioni IFC (add/remove) passano per `tool.Ifc.Operator` → undo/redo automatico.
- L'UI legge da `data.py` (cache invalidata da handler su undo/redo/load).
- L'host nuvola è linkato all'IfcAnnotation (`tool.Ifc.link`) → Bonsai persiste il placement; il clip box è solo di sessione.
- Visibilità via PCV: flag `draw` in `PCVMechanist.cache` (erase), non hide dell'oggetto.
- API PCV: load `PCVStoker.load()` + `PCVMechanist`, clip via `shader.clip_planes_from_bbox_object`.

## TODO

- [x] Clip via PCV: `shader.clip_planes_from_bbox_object` + `..._live` + `clip_enabled`
- [x] Visibilità via PCV erase; clip box = cube 3 m; select/show clip box
- [x] Refactor Bonsai-standard (core/tool/data/operator/prop/ui), solo entità IFC standard
- [x] Host persistente (IfcAnnotation + placement) ricaricabile in posizione
- [x] Fallback GPU integrato per PLY quando PCV non è installato (viewer.py)
- [ ] Gestione offset georef (false origin grandi: Gauss-Boaga/UTM)
- [ ] Supporto per altri formati ASCII (XYZ, PTS)

## License

GPL v3 (compatible with Blender ecosystem)

## Crediti

- **Point Cloud Visualizer** by Jakub Uhlík — [acquista su Blender Market](https://blendermarket.com/products/point-cloud-visualizer)
- **Bonsai** by IfcOpenShell & community
