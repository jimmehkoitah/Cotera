"""Bake the agent library and Cotera links into one static page, dist/index.html.
Each private page from data/custom.json is written to its own file, dist/for/<code>.json, so the public page never contains it."""
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
DIST = HERE / 'dist'
SOURCE = HERE.parent / 'cotera-bingo' / 'agent-library' / 'cotera-agent-library.json'
LOGO = HERE.parent / 'cotera-bingo' / 'public' / 'brand' / 'cotera-logo.svg'
ROLES = [  # the six GTM roles shown in the library, in display order
    ('sales', 'Sales & prospecting', 'Sales teams, account executives and SDRs'),
    ('marketing', 'Marketing & growth', 'Demand generation, growth, ABM and field marketing'),
    ('customers', 'Customer success & accounts', 'Customer success, CS Ops, account management and renewals'),
    ('revops', 'Revenue & marketing ops', 'RevOps, sales ops, marketing ops, CRM data and reporting'),
    ('market', 'Strategy & market intelligence', 'Strategic BD, advisory, research and product marketing'),
    ('technology', 'Systems & AI', 'IT, GTM engineering, business systems and AI tools'),
]
LABELS = {label for _, label, _ in ROLES}


def steps(how):
    """'a → b' or ['a', 'b'] -> ['A', 'B']"""
    parts = how.split('→') if isinstance(how, str) else how
    return [s.strip()[0].upper() + s.strip()[1:] for s in parts if s.strip()]


agents = []
for a in json.loads(SOURCE.read_text())['agents']:
    problems = [p for p in a['problems'] if LABELS & set(p['roles'])]
    if not problems:
        continue  # agents that only cover retired roles stay out of the library
    agents.append({
        'id': a['id'], 'name': a['name'], 'type': a['type'], 'wedge': a['wedge'],
        'what': a['what_it_does'], 'how': steps(a['how_it_works']),
        'data': a['data_it_uses'], 'who': a['who_uses_it'], 'first': a['first_version'],
        'measure': a['measure'], 'ask': a['ask_them'],
        'problems': [{'id': p['id'], 'card': p['card'], 'statement': p['statement'], 'how': p['how_it_solves'], 'ask': p['ask'], 'roles': [r for r in p['roles'] if r in LABELS]} for p in problems],
    })
roles = []
for rid, label, desc in ROLES:
    probs = sorted(({'id': p['id'], 'card': p['card'], 'statement': p['statement'], 'agent': a['id']}
                    for a in agents for p in a['problems'] if label in p['roles']), key=lambda p: p['id'])
    roles.append({'id': rid, 'label': label, 'description': desc, 'problems': probs})

ids = {a['id'] for a in agents}
links = {k: v for k, v in json.loads((HERE / 'data' / 'links.json').read_text()).items() if not k.startswith('_') and v}
for k in links:
    assert k in ids, f'links.json: unknown agent {k}'
custom = {k: v for k, v in json.loads((HERE / 'data' / 'custom.json').read_text()).items() if not k.startswith('_')}
for code, space in custom.items():
    assert re.fullmatch(r'[A-Za-z0-9_-]+', code), f'custom.json: page code {code!r} may only use letters, digits, - and _'
    for key in ('for', 'title', 'agents'):
        assert key in space, f'custom.json {code}: missing "{key}"'
    for ref in space.get('library', []):
        assert ref in ids, f'custom.json {code}: unknown library agent {ref}'
    for a in space['agents']:
        for key in ('id', 'name', 'what', 'how'):
            assert a.get(key), f'custom.json {code}: an agent is missing "{key}"'
        a['how'] = steps(a['how'])
        for key in ('type', 'wedge', 'data', 'who', 'first', 'measure', 'ask', 'link'):
            a.setdefault(key, '')
        a.setdefault('problems', [])

data = json.dumps({'agents': agents, 'roles': roles, 'links': links}, ensure_ascii=False, separators=(',', ':'))
data = data.replace('</', '<\\/')  # keep the inline script safe
logo = LOGO.read_text().strip()
html = (HERE / 'template.html').read_text().replace('__LOGO__', logo).replace('__DATA__', data)
DIST.mkdir(exist_ok=True)
(DIST / 'index.html').write_text(html, encoding='utf-8')
shutil.rmtree(DIST / 'for', ignore_errors=True)  # pages removed from custom.json stop being served
(DIST / 'for').mkdir()
for code, space in custom.items():
    (DIST / 'for' / f'{code}.json').write_text(json.dumps(space, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'dist/index.html: {len(agents)} agents, {sum(len(r["problems"]) for r in roles)} role listings, '
      f'{len({p["id"] for a in agents for p in a["problems"]})} unique problems, {len(links)} Cotera links, {len(html)//1024} KB; '
      f'dist/for: {len(custom)} private pages')
