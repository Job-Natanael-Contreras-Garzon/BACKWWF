import math
from typing import List, Dict, Any
from datetime import datetime

class IndicatorsService:
    @staticmethod
    def calculate_trap_days(data: List[Any]) -> float:
        """Calcula Días-trampa REALES sumando el span de cada cámara (max - min date + 1)"""
        if not data:
            return 0.0
            
        cam_dates = {}
        for row in data:
            cam = row.id_camara
            dt = row.fecha_hora
            if not dt:
                continue
            if cam not in cam_dates:
                cam_dates[cam] = {"min": dt, "max": dt}
            else:
                if dt < cam_dates[cam]["min"]:
                    cam_dates[cam]["min"] = dt
                if dt > cam_dates[cam]["max"]:
                    cam_dates[cam]["max"] = dt
                    
        total_days = 0.0
        for cam, dates in cam_dates.items():
            span_seconds = (dates["max"] - dates["min"]).total_seconds()
            total_days += (span_seconds / 86400) + 1
            
        return total_days

    @staticmethod
    def calculate_frequency(data: List[Any]) -> Dict[str, Any]:
        total_bruto = len(data)
        total_eventos = 0
        stats_map = {}

        for row in data:
            sp = row.especie
            if sp not in stats_map:
                stats_map[sp] = {"bruto": 0, "estadistico": 0}
            
            stats_map[sp]["bruto"] += 1
            
            if getattr(row, "evento_independiente", 0) == 1:
                stats_map[sp]["estadistico"] += 1
                total_eventos += 1

        filas = []
        for sp, counts in stats_map.items():
            b_pct = round((counts["bruto"] / total_bruto) * 100, 1) if total_bruto > 0 else 0
            e_pct = round((counts["estadistico"] / total_eventos) * 100, 1) if total_eventos > 0 else 0
            filas.append({
                "especie": sp,
                "bruto_ni": counts["bruto"],
                "bruto_pct": b_pct,
                "estad_eventos": counts["estadistico"],
                "estad_pct": e_pct
            })
            
        filas.sort(key=lambda x: x["bruto_ni"], reverse=True)

        return {
            "total_bruto": total_bruto,
            "total_eventos": total_eventos,
            "filas": filas
        }

    @staticmethod
    def calculate_diversity(data: List[Any]) -> Dict[str, Any]:
        counts_bruto = {}
        counts_estad = {}
        n_bruto = 0
        n_estad = 0

        for row in data:
            sp = row.especie
            counts_bruto[sp] = counts_bruto.get(sp, 0) + 1
            n_bruto += 1

            if getattr(row, "evento_independiente", 0) == 1:
                counts_estad[sp] = counts_estad.get(sp, 0) + 1
                n_estad += 1

        def calc_indices(counts_map: Dict[str, int], total_n: int) -> Dict[str, Any]:
            if total_n == 0:
                return {"S": 0, "shannon": 0, "simpson": 0, "dominante": None}
            
            shannon_sum = 0.0
            simpson_sum = 0.0
            dominante = None
            max_c = -1
            
            for sp, count in counts_map.items():
                pi = count / total_n
                shannon_sum += pi * math.log(pi)
                simpson_sum += pi ** 2
                
                if count > max_c:
                    max_c = count
                    dominante = sp
                    
            return {
                "S": len(counts_map),
                "shannon": round(-shannon_sum, 3),
                "simpson": round(1 - simpson_sum, 3),
                "dominante": dominante
            }

        return {
            "bruto": calc_indices(counts_bruto, n_bruto),
            "estadistico": calc_indices(counts_estad, n_estad)
        }

    @staticmethod
    def calculate_rai(data: List[Any]) -> Dict[str, Any]:
        trap_days_total = IndicatorsService.calculate_trap_days(data)
        freq = IndicatorsService.calculate_frequency(data)
        filas = []
        for item in freq["filas"]:
            rai_bruto = round((item["bruto_ni"] / trap_days_total) * 100, 2) if trap_days_total > 0 else 0
            rai_estad = round((item["estad_eventos"] / trap_days_total) * 100, 2) if trap_days_total > 0 else 0
            filas.append({
                "especie": item["especie"],
                "rai_bruto": rai_bruto,
                "rai_estadistico": rai_estad,
                "eventos": item["estad_eventos"]
            })
            
        return {
            "dias_trampa_total": round(trap_days_total, 1),
            "filas": filas
        }

    @staticmethod
    def calculate_rai_mensual(data: List[Any]) -> Dict[str, Any]:
        """Calcula RAI (Distribución estacional) por mes - 3b"""
        meses_set = set()
        stats = {}
        
        # Filtrar solo eventos independientes y recolectar
        for row in data:
            if getattr(row, "evento_independiente", 0) != 1:
                continue
                
            sp = row.especie
            dt = row.fecha_hora
            if not dt:
                continue
            
            mes = dt.month
            meses_set.add(mes)
            
            if sp not in stats:
                stats[sp] = {"total": 0, "meses": {}}
            
            stats[sp]["meses"][mes] = stats[sp]["meses"].get(mes, 0) + 1
            stats[sp]["total"] += 1
            
        meses = sorted(list(meses_set))
        filas = []
        totales_por_mes = {f"m{m}": 0 for m in meses}
        
        # Ordenamos usando la frecuencia bruta para mantener el patrón de orden
        freq = IndicatorsService.calculate_frequency(data)
        orden_especies = [f["especie"] for f in freq["filas"]]
        
        for sp in orden_especies:
            if sp not in stats:
                continue
                
            fila = {"especie": sp}
            for m in meses:
                v = stats[sp]["meses"].get(m, 0)
                fila[f"m{m}"] = v
                totales_por_mes[f"m{m}"] += v
                
            fila["total"] = stats[sp]["total"]
            filas.append(fila)
            
        return {
            "meses": meses,
            "filas": filas,
            "totales": totales_por_mes
        }

    @staticmethod
    def calculate_actividad(data: List[Any]) -> Dict[str, Any]:
        """7b. Actividad diaria (Weckel)"""
        stats = {}
        for row in data:
            sp = row.especie
            pw = getattr(row, "periodoweckel", None) or getattr(row, "periodo_weckel", None)
            
            if sp not in stats:
                stats[sp] = {"n": 0, "nocturno": 0, "diurno": 0, "crepuscular": 0}
                
            stats[sp]["n"] += 1
            if pw in ["nocturno", "diurno", "crepuscular"]:
                stats[sp][pw] += 1
                
        freq = IndicatorsService.calculate_frequency(data)
        orden_especies = [f["especie"] for f in freq["filas"]]
        
        filas = []
        for sp in orden_especies:
            s = stats.get(sp)
            if not s or s["n"] == 0:
                continue
                
            n = s["n"]
            filas.append({
                "especie": sp,
                "n": n,
                "pct_nocturno": round(s["nocturno"] / n * 100, 1),
                "pct_diurno": round(s["diurno"] / n * 100, 1),
                "pct_crepuscular": round(s["crepuscular"] / n * 100, 1)
            })
            
        return {"filas": filas}

    @staticmethod
    def calculate_ocupacion(data: List[Any]) -> Dict[str, Any]:
        """Calcula ocupacion por especie: (Estaciones con especie) / (Total estaciones)"""
        estaciones_totales = set()
        estaciones_por_especie = {}

        for row in data:
            cam = row.id_camara
            sp = row.especie
            estaciones_totales.add(cam)
            if sp not in estaciones_por_especie:
                estaciones_por_especie[sp] = set()
            if getattr(row, "evento_independiente", 0) == 1:
                estaciones_por_especie[sp].add(cam)

        total_camaras = len(estaciones_totales)
        filas = []
        for sp, cams in estaciones_por_especie.items():
            ocupacion = len(cams) / total_camaras if total_camaras > 0 else 0
            filas.append({
                "especie": sp,
                "estaciones_presente": len(cams),
                "ocupacion_pct": round(ocupacion * 100, 2)
            })

        return {
            "total_estaciones": total_camaras,
            "filas": sorted(filas, key=lambda x: x["ocupacion_pct"], reverse=True)
        }

    @staticmethod
    def calculate_temperatura(data: List[Any]) -> Dict[str, Any]:
        """Calcula temperatura media por especie usando temp_media (si estA disponible)"""
        stats = {}
        for row in data:
            if getattr(row, "evento_independiente", 0) != 1:
                continue
                
            sp = row.especie
            temp = getattr(row, "temp_media", None)
            if temp is None:
                continue
                
            if sp not in stats:
                stats[sp] = {"sum": 0.0, "count": 0, "min": temp, "max": temp}
                
            stats[sp]["sum"] += temp
            stats[sp]["count"] += 1
            if temp < stats[sp]["min"]:
                stats[sp]["min"] = temp
            if temp > stats[sp]["max"]:
                stats[sp]["max"] = temp
                
        filas = []
        for sp, s in stats.items():
            filas.append({
                "especie": sp,
                "n": s["count"],
                "temp_min": round(s["min"], 1),
                "temp_max": round(s["max"], 1),
                "temp_promedio": round(s["sum"] / s["count"], 1)
            })
            
        return {"filas": sorted(filas, key=lambda x: x["especie"])}

    @staticmethod
    def calculate_eventos_independientes(data: List[Any]) -> Dict[str, Any]:
        """Resume eventos independientes por especie y estaciA3n"""
        stats = {}
        for row in data:
            sp = row.especie
            cam = row.id_camara
            
            if sp not in stats:
                stats[sp] = {"total_bruto": 0, "eventos_independientes": 0, "por_camara": {}}
                
            stats[sp]["total_bruto"] += 1
            
            is_indep = getattr(row, "evento_independiente", 0)
            if is_indep == 1:
                stats[sp]["eventos_independientes"] += 1
                stats[sp]["por_camara"][cam] = stats[sp]["por_camara"].get(cam, 0) + 1
                
        filas = []
        for sp, s in stats.items():
            filas.append({
                "especie": sp,
                "bruto": s["total_bruto"],
                "independientes": s["eventos_independientes"],
                "desglose_camaras": s["por_camara"]
            })
            
        return {"filas": sorted(filas, key=lambda x: x["independientes"], reverse=True)}

    @staticmethod
    def calculate_mapa_calor(data: List[Any]) -> Dict[str, Any]:
        """Mapa de calor: Frecuencia de eventos independientes por Hora y por DA-a de la semana"""
        matriz = {}
        # Inicializar matriz [0-23][0-6]
        for h in range(24):
            matriz[h] = {d: 0 for d in range(7)}
            
        for row in data:
            if getattr(row, "evento_independiente", 0) != 1:
                continue
                
            dt = getattr(row, "fecha_hora", None)
            if not dt:
                continue
                
            hora = dt.hour
            dia_sem = dt.weekday() # 0 = Lunes, 6 = Domingo
            matriz[hora][dia_sem] += 1
            
        # Transformar a formato para frontend
        filas = []
        dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        for h in range(24):
            fila = {"hora": h}
            for d in range(7):
                fila[dias[d]] = matriz[h][d]
            filas.append(fila)
            
        return {"dias": dias, "matriz": filas}

    @staticmethod
    def calculate_gremios(data: List[Any]) -> Dict[str, Any]:
        """Calcula estadisticas por gremio trofico. Como no esta en BD, usamos un mapeo por defecto"""
        GREMIOS_MAP = {
            'southern lesser long-tailed opossum': 'Omnivoro',
            'brown brocket deer': 'Herbivoro',
            'collared peccary': 'Frugivoro/Omnivoro',
            'armadillo': 'Insectivoro',
            'brazilian rabbit': 'Herbivoro',
            'crab-eating fox': 'Carnivoro/Omnivoro',
            'ocelot': 'Carnivoro',
            'giant anteater': 'Insectivoro',
            'pampas deer': 'Herbivoro',
            'tayra': 'Omnivoro',
            'capybara': 'Herbivoro',
            'black howler monkey': 'Frugivoro/Folivoro',
            'brazilian tapir': 'Herbivoro',
            'white-lipped peccary': 'Frugivoro/Omnivoro',
            'giant armadillo': 'Insectivoro',
            'squirrel': 'Granivoro/Frugivoro',
            'tamandua': 'Insectivoro',
            'white-nosed coati': 'Omnivoro',
            'common opossum': 'Omnivoro',
            'gray four-eyed opossum': 'Omnivoro',
            'crab-eating raccoon': 'Omnivoro',
        }
        
        stats = {}
        total = 0
        for row in data:
            if getattr(row, "evento_independiente", 0) != 1:
                continue
                
            sp_lower = getattr(row, "especie", "").lower()
            gremio = GREMIOS_MAP.get(sp_lower, 'Desconocido')
            
            stats[gremio] = stats.get(gremio, 0) + 1
            total += 1
            
        filas = []
        for gremio, count in stats.items():
            filas.append({
                "gremio": gremio,
                "eventos": count,
                "pct": round((count / total) * 100, 1) if total > 0 else 0
            })
            
        return {
            "total_eventos": total,
            "filas": sorted(filas, key=lambda x: x["eventos"], reverse=True)
        }
