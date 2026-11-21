"""Аналитика вопросов по переписке, без подмены ответов доставкой или приветствиями."""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from bot.corpus import faq_by_id
from bot.storage import _connect, init_db
from bot.textutil import basic_normalize
from bot.rag import load_knowledge

BISHKEK = timezone(timedelta(hours=6))


def redact(text):
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[email]", text)
    return re.sub(r"\+?\d[\d ()-]{6,}\d", "[номер]", text)[:240]


def build_analytics(days=7, channel="", now=None):
    init_db()
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(BISHKEK).date()
    start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), BISHKEK) if days else None
    params = []
    clauses = ["m.direction='inbound'", "m.sender='customer'", "m.mode!='selection'"]
    if start:
        clauses.append("m.created_at >= ?")
        params.append(start.astimezone(timezone.utc).isoformat(timespec='seconds'))
    if channel in {"telegram", "whatsapp"}:
        clauses.append("c.channel=?")
        params.append(channel)
    with _connect() as db:
        rows = db.execute(
            "SELECT m.id,m.chat_id,m.text,m.created_at,c.channel,r.sender,r.mode, "
            "d.status AS delivery,a.payload FROM messages m JOIN chats c ON c.id=m.chat_id "
            "LEFT JOIN messages r ON r.chat_id=m.chat_id AND r.direction='outbound' AND r.id>m.id "
            "AND r.id<COALESCE((SELECT MIN(n.id) FROM messages n WHERE n.chat_id=m.chat_id "
            "AND n.direction='inbound' AND n.id>m.id),9223372036854775807) "
            "LEFT JOIN deliveries d ON d.message_id=r.id "
            "LEFT JOIN answer_details a ON a.message_id=r.id WHERE " + " AND ".join(clauses) + " ORDER BY m.id,r.id",
            params,
        ).fetchall()
    grouped = {}
    for row in rows:
        entry = grouped.setdefault(row['id'], {'question':dict(row), 'responses':[]})
        if row['sender']:
            entry['responses'].append(dict(row))
    outcomes = Counter()
    channels = Counter()
    topics = Counter()
    questions = {}
    gaps = {}
    daily = defaultdict(Counter)
    rag_titles = {row['id']: row['question'] for row in load_knowledge()}
    rag_titles['tariff-prices'] = 'Цены тарифов для подключения'
    for entry in grouped.values():
        question, replies = entry['question'], entry['responses']
        if question['text'].startswith('/') or any(r['mode'] in {'greeting','command'} for r in replies):
            continue
        if any(r['sender']=='operator' for r in replies):
            outcome = 'operator'
        elif any(r['delivery']=='failed' for r in replies):
            outcome = 'failed'
        elif any(r['mode'] in {'direct','rag','selected'} for r in replies):
            outcome = 'answered'
        elif any(r['mode']=='buttons' for r in replies):
            outcome = 'uncertain'
        elif any(r['mode'] in {'refuse','handoff'} for r in replies):
            outcome = 'unanswered'
        else:
            outcome = 'pending'
        outcomes[outcome] += 1
        channels[question['channel']] += 1
        day = datetime.fromisoformat(question['created_at']).astimezone(BISHKEK).date().isoformat()
        daily[day]['total'] += 1
        daily[day]['answered'] += outcome=='answered'
        label = redact(question['text'])
        key = basic_normalize(label)
        bucket = questions.setdefault(key, {'text':label, 'count':0, 'chat_id':question['chat_id']})
        bucket['count'] += 1
        bucket['chat_id'] = question['chat_id']
        if outcome in {'unanswered','uncertain','pending','failed'}:
            gap = gaps.setdefault(key, {'text':label,'count':0,'chat_id':question['chat_id'],'outcome':outcome})
            gap['count'] += 1
            gap['chat_id'] = question['chat_id']
        for reply in replies:
            if reply['mode'] not in {'direct','rag','selected'}:
                continue
            details = json.loads(reply['payload']) if reply['payload'] else {}
            faq = faq_by_id().get(details.get('faq_id'))
            rag_id = details.get('rag_id')
            topic = faq['question_ru'] if faq else rag_titles.get(rag_id) or rag_id or 'Без сохранённой темы'
            topics[topic] += 1
            break
    total = sum(outcomes.values())
    horizon = min(days or 30, 30)
    timeline = []
    for offset in range(horizon-1,-1,-1):
        day = today-timedelta(days=offset)
        counts = daily[day.isoformat()]
        timeline.append({'label':day.strftime('%d.%m'), **{'total':counts['total'],'answered':counts['answered']}})
    maximum = max((point['total'] for point in timeline), default=0) or 1
    for point in timeline:
        point['height'] = round(point['total']/maximum*100)
    return {'total':total,'answered':outcomes['answered'], 'rate':round(outcomes['answered']/total*100,1) if total else 0,
            'gaps':sum(outcomes[key] for key in ('unanswered','uncertain','pending','failed')),
            'outcomes':dict(outcomes),'channels':dict(channels), 'timeline':timeline,
            'questions':sorted(questions.values(),key=lambda x:-x['count'])[:10],
            'unanswered':sorted(gaps.values(),key=lambda x:-x['count'])[:15],
            'topics':[{'title':title,'count':count} for title,count in topics.most_common(8)]}
