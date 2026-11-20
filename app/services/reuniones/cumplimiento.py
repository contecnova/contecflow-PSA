"""Controles del asistente de reuniones para el informe de cumplimiento
(`app/services/informe_de_cumplimiento.py`). Se miden ahora, sobre la empresa."""
from __future__ import annotations

from datetime import datetime, timezone


def controles(db, org: str, _control) -> list[dict]:
    from app.models.ai_chat import AIMeeting
    from app.models.reuniones import AIMeetingAudio
    from app.services.reuniones import config
    from app.services.reuniones.transcripcion import proveedores_configurados
    ahora = datetime.now(timezone.utc)
    cfg = config.leer(db, org)
    salida = []

    # 1. Terceros: el bot y el STT externo solo con contrato de encargo.
    bot_sin_contrato = bool(cfg["bots"]["enabled"] and not cfg["bots"].get("contract_reference"))
    externos = [p for p in proveedores_configurados(db, org) if p not in config.STT_LOCALES]
    stt_sin_contrato = bool(cfg["transcription"]["allow_external_stt"]
                            and not cfg["transcription"].get("external_stt_contract"))
    activos = cfg["bots"]["enabled"] or cfg["transcription"]["allow_external_stt"]
    salida.append(_control(
        "meetings_external_processors",
        "attention" if bot_sin_contrato or stt_sin_contrato else ("pass" if activos else "info"),
        {"bot_enabled": cfg["bots"]["enabled"], "bot_provider": cfg["bots"]["provider"],
         "bot_contract": bool(cfg["bots"].get("contract_reference")),
         "external_stt_allowed": cfg["transcription"]["allow_external_stt"],
         "external_stt_contract": bool(cfg["transcription"].get("external_stt_contract")),
         "external_stt_configured": externos,
         "connectors": {k: cfg[k]["enabled"] for k in ("teams", "zoom", "meet")}},
        "reuniones.config (bots, transcription, conectores)", ("RGPD art. 28", "ISO27001 A.5.19", "ISO27001 A.5.20")))

    # 2. Retención separada: nada vencido sin purgar (fuera de bloqueos legales, que se informan).
    audio_vencido = db.query(AIMeetingAudio).filter(AIMeetingAudio.organization_id == org,
                                                    AIMeetingAudio.expires_at < ahora).count()
    trans_vencidas = db.query(AIMeeting).filter(AIMeeting.organization_id == org,
                                                AIMeeting.transcript_expires_at < ahora,
                                                AIMeeting.transcript_purged_at.is_(None)).count()
    salida.append(_control(
        "meetings_retention", "pass" if audio_vencido == 0 and trans_vencidas == 0 else "attention",
        {"audio_days": cfg["retention"]["audio_days"], "transcript_days": cfg["retention"]["transcript_days"],
         "expired_audio_chunks_pending": audio_vencido, "expired_transcripts_pending": trans_vencidas},
        "ai_meeting_audio.expires_at y ai_meetings.transcript_expires_at vencidos (los bloqueados legalmente cuentan)",
        ("RGPD art. 5.1.e", "ISO27001 A.5.33")))

    # 3. Consentimiento y aviso.
    sin_aviso = db.query(AIMeeting).filter(AIMeeting.organization_id == org, AIMeeting.origin == "recording",
                                           AIMeeting.notice_confirmed_at.is_(None)).count()
    exige = bool(cfg["consent"]["require_consent"])
    if exige:
        from app.models.reuniones import AIMeetingParticipant
        analizadas_sin = (db.query(AIMeeting.id).join(AIMeetingParticipant,
                                                       AIMeetingParticipant.meeting_id == AIMeeting.id)
                          .filter(AIMeeting.organization_id == org, AIMeeting.consent_required.is_(True),
                                  AIMeeting.status == "lista", AIMeetingParticipant.consent.is_(None))
                          .distinct().count())
    else:
        analizadas_sin = 0
    estado = "attention" if sin_aviso or analizadas_sin else ("pass" if exige else "info")
    salida.append(_control(
        "meetings_consent", estado,
        {"notice_required": cfg["consent"]["notice_required"], "require_consent": exige,
         "recordings_without_notice": sin_aviso, "analyzed_with_pending_consent": analizadas_sin},
        "ai_meetings.notice_confirmed_at + ai_meeting_participants.consent", ("RGPD art. 6", "RGPD art. 13")))
    return salida
