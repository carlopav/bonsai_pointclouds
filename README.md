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
- Point Cloud Visualizer v3 addon

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

Ogni nuvola è un **IfcAnnotation** (`ObjectType = "PointCloud"`), con:
- **IfcDocumentReference** (via `IfcRelAssociatesDocument`) che porta il path del file (`Location`).
- Pset `Pset_PointCloud_120g`: `Location`, `Scale`, `ScanDate`, `IsVisible`, `IsClipped`.

Scrittura sempre tramite `ifcopenshell.api` (`root.create_entity`, `document.add_reference`, `pset.add_pset`/`edit_pset`), così ownership history e undo/redo sono gestiti da Bonsai.

## Note Tecniche

- Le mutazioni IFC passano per `tool.Ifc.Operator` → undo/redo automatico (nessuna transazione manuale).
- L'UI legge da `data.py` (cache invalidata da handler su undo/redo/load).
- Oggetti Blender (host nuvola, clip box) non sono persistenti; sono linkati all'elemento IFC via custom prop `bonsai_pointcloud_id`.
- API PCV: load `PCVStoker.load()` + `PCVMechanist`, clip via `shader.clip_planes_from_bbox_object`.

## TODO

- [x] Clip via PCV: `shader.clip_planes_from_bbox_object` + `..._live` + `clip_enabled` (confermato dal sorgente PCV v3)
- [x] Toggle visibility/clipping funzionanti, stato persistito nel Pset
- [x] Refactor allineato agli standard Bonsai (core/tool/data/operator/prop/ui)
- [ ] Gestione placement/georef IFC → world matrix (blender offset di Bonsai)
- [ ] UI per editare parametri (scala, rinomina)
- [ ] Supporto per altri formati ASCII (XYZ, PTS)

## License

GPL v3 (compatible with Blender ecosystem)

## Crediti

- **Point Cloud Visualizer** by Jakub Uhlík
- **Bonsai** by IfcOpenShell & community
