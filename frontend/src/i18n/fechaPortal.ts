/**
 * Textos del selector de fecha del kit en los 8 idiomas del portal de
 * clientes (16-11-2026). El kit trae es/en/zh (`fecha.*` de i18n/langs); el
 * portal pasa estos con `textos` e `idioma` a `CampoFecha`. Van aparte de
 * `i18n/portal/*` para no tocar los diccionarios del portal desde el kit.
 */
import type { TextosDeFecha } from '../components/ui/SelectorDeFecha'

export const TEXTOS_FECHA_PORTAL: Record<string, TextosDeFecha> = {
  es: { abrir_calendario: 'Abrir calendario', abrir_hora: 'Elegir hora', elegir_fecha: 'Elegir fecha', elegir_hora: 'Elegir hora', mes_anterior: 'Mes anterior', mes_siguiente: 'Mes siguiente', mes: 'Mes', anio: 'Año', hora: 'Hora', horas: 'Horas', minutos: 'Minutos', hoy: 'Hoy', ahora: 'Ahora', listo: 'Listo', invalida: 'Fecha no válida', min: 'No puede ser anterior a {fecha}', max: 'No puede ser posterior a {fecha}', rango: 'Rango de fechas', desde: 'Desde', hasta: 'Hasta' },
  en: { abrir_calendario: 'Open calendar', abrir_hora: 'Choose time', elegir_fecha: 'Choose date', elegir_hora: 'Choose time', mes_anterior: 'Previous month', mes_siguiente: 'Next month', mes: 'Month', anio: 'Year', hora: 'Time', horas: 'Hours', minutos: 'Minutes', hoy: 'Today', ahora: 'Now', listo: 'Done', invalida: 'Invalid date', min: 'Cannot be before {fecha}', max: 'Cannot be after {fecha}', rango: 'Date range', desde: 'From', hasta: 'To' },
  fr: { abrir_calendario: 'Ouvrir le calendrier', abrir_hora: "Choisir l'heure", elegir_fecha: 'Choisir une date', elegir_hora: "Choisir l'heure", mes_anterior: 'Mois précédent', mes_siguiente: 'Mois suivant', mes: 'Mois', anio: 'Année', hora: 'Heure', horas: 'Heures', minutos: 'Minutes', hoy: "Aujourd'hui", ahora: 'Maintenant', listo: 'Terminé', invalida: 'Date non valide', min: 'Ne peut pas être antérieure au {fecha}', max: 'Ne peut pas être postérieure au {fecha}', rango: 'Plage de dates', desde: 'Du', hasta: 'Au' },
  de: { abrir_calendario: 'Kalender öffnen', abrir_hora: 'Uhrzeit wählen', elegir_fecha: 'Datum wählen', elegir_hora: 'Uhrzeit wählen', mes_anterior: 'Vorheriger Monat', mes_siguiente: 'Nächster Monat', mes: 'Monat', anio: 'Jahr', hora: 'Uhrzeit', horas: 'Stunden', minutos: 'Minuten', hoy: 'Heute', ahora: 'Jetzt', listo: 'Fertig', invalida: 'Ungültiges Datum', min: 'Darf nicht vor dem {fecha} liegen', max: 'Darf nicht nach dem {fecha} liegen', rango: 'Datumsbereich', desde: 'Von', hasta: 'Bis' },
  pt: { abrir_calendario: 'Abrir calendário', abrir_hora: 'Escolher hora', elegir_fecha: 'Escolher data', elegir_hora: 'Escolher hora', mes_anterior: 'Mês anterior', mes_siguiente: 'Mês seguinte', mes: 'Mês', anio: 'Ano', hora: 'Hora', horas: 'Horas', minutos: 'Minutos', hoy: 'Hoje', ahora: 'Agora', listo: 'Concluído', invalida: 'Data inválida', min: 'Não pode ser anterior a {fecha}', max: 'Não pode ser posterior a {fecha}', rango: 'Intervalo de datas', desde: 'De', hasta: 'Até' },
  it: { abrir_calendario: 'Apri calendario', abrir_hora: "Scegli l'ora", elegir_fecha: 'Scegli la data', elegir_hora: "Scegli l'ora", mes_anterior: 'Mese precedente', mes_siguiente: 'Mese successivo', mes: 'Mese', anio: 'Anno', hora: 'Ora', horas: 'Ore', minutos: 'Minuti', hoy: 'Oggi', ahora: 'Adesso', listo: 'Fatto', invalida: 'Data non valida', min: 'Non può essere prima del {fecha}', max: 'Non può essere dopo il {fecha}', rango: 'Intervallo di date', desde: 'Dal', hasta: 'Al' },
  pl: { abrir_calendario: 'Otwórz kalendarz', abrir_hora: 'Wybierz godzinę', elegir_fecha: 'Wybierz datę', elegir_hora: 'Wybierz godzinę', mes_anterior: 'Poprzedni miesiąc', mes_siguiente: 'Następny miesiąc', mes: 'Miesiąc', anio: 'Rok', hora: 'Godzina', horas: 'Godziny', minutos: 'Minuty', hoy: 'Dziś', ahora: 'Teraz', listo: 'Gotowe', invalida: 'Nieprawidłowa data', min: 'Nie może być wcześniejsza niż {fecha}', max: 'Nie może być późniejsza niż {fecha}', rango: 'Zakres dat', desde: 'Od', hasta: 'Do' },
  zh: { abrir_calendario: '打开日历', abrir_hora: '选择时间', elegir_fecha: '选择日期', elegir_hora: '选择时间', mes_anterior: '上个月', mes_siguiente: '下个月', mes: '月', anio: '年', hora: '时间', horas: '小时', minutos: '分钟', hoy: '今天', ahora: '现在', listo: '完成', invalida: '日期无效', min: '不能早于 {fecha}', max: '不能晚于 {fecha}', rango: '日期范围', desde: '开始', hasta: '结束' },
}

export function textosDeFechaDelPortal(idioma: string): TextosDeFecha {
  return TEXTOS_FECHA_PORTAL[idioma] ?? TEXTOS_FECHA_PORTAL.en
}
