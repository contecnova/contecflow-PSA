#!/usr/bin/env python3
"""
Smoke test simple sin necesidad de Playwright - detecta claves sin traducir.
"""

import re
from html.parser import HTMLParser
import time
import urllib.request
import urllib.error

class HeadingParser(HTMLParser):
    """Parser para extraer headings del HTML"""
    def __init__(self):
        super().__init__()
        self.headings = []
        self.in_heading = False
        self.current_text = []
        
    def handle_starttag(self, tag, attrs):
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.in_heading = True
            self.current_text = []
        
    def handle_endtag(self, tag):
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and self.in_heading:
            text = ''.join(self.current_text).strip()
            if text and len(text) < 200:
                self.headings.append({
                    'element': tag,
                    'text': text
                })
            self.in_heading = False
            self.current_text = []
    
    def handle_data(self, data):
        if self.in_heading:
            self.current_text.append(data)

def is_untranslated(text):
    """Detecta si el texto parece una clave sin traducir"""
    text_lower = text.lower().strip()
    
    # Patrones a detectar
    patterns = [
        r'^title$',
        r'^subtitle$',
        r'^[a-z_]+\.[a-z_]+$',  # module.key pattern
        r'.*\btitle\b.*',
        r'.*\bsubtitle\b.*'
    ]
    
    return any(re.match(pattern, text_lower) for pattern in patterns)

routes = [
    '/dashboard',
    '/projects',
    '/wiki',
    '/meetings-ai',
    '/resource-forecast',
    '/resource-scheduler',
    '/okrs',
    '/performance-reviews',
    '/training',
    '/invoices',
    '/revenue',
    '/budgets',
    '/rate-cards',
    '/scenarios',
    '/cmdb',
    '/sla-calendars',
    '/risk-scores',
    '/nexus-agent',
    '/oracle',
    '/project-templates',
    '/import',
    '/mfa',
    '/governance',
    '/organizations',
    '/enterprise',
    '/webhook-log',
]

results = {
    'passed': 0,
    'failed': 0,
    'untranslated_headers': [],
    'detailed_results': []
}

print("\n" + "="*60)
print("SMOKE TEST COMPLETO - DETECTANDO CLAVES SIN TRADUCIR")
print("="*60 + "\n")

for route in routes:
    try:
        url = f"http://localhost:3000{route}"
        print(f"Testing {route}...", end='', flush=True)
        
        # Hacer petición
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                status_code = response.status
                html_content = response.read().decode('utf-8', errors='ignore')
        except urllib.error.HTTPError as e:
            status_code = e.code
            html_content = e.read().decode('utf-8', errors='ignore') if hasattr(e, 'read') else ""
        
        if status_code >= 400:
            results['failed'] += 1
            results['detailed_results'].append({
                'route': route,
                'status': status_code,
                'error': f"HTTP {status_code}"
            })
            print(f" ❌ ({status_code})")
            continue
        
        # Parsear HTML para buscar headings
        parser = HeadingParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            print(f" ⚠️  (parse error: {str(e)[:20]})")
            continue
        
        headings = parser.headings
        
        # Detectar headings sin traducir
        untranslated = [h for h in headings if is_untranslated(h['text'])]
        
        results['passed'] += 1
        
        if untranslated:
            results['untranslated_headers'].append({
                'route': route,
                'count': len(untranslated),
                'items': untranslated
            })
            print(f" ⚠️  ({len(untranslated)} sin traducir de {len(headings)})")
        else:
            print(f" ✅ ({len(headings)} headings OK)")
        
        results['detailed_results'].append({
            'route': route,
            'status': status_code,
            'headers_found': len(headings),
            'untranslated_count': len(untranslated),
            'untranslated': untranslated
        })
        
        time.sleep(0.3)  # Pequeña pausa entre peticiones
        
    except urllib.error.URLError as e:
        if 'timeout' in str(e).lower():
            results['failed'] += 1
            results['detailed_results'].append({
                'route': route,
                'error': 'Timeout'
            })
            print(f" ⏱️  (Timeout)")
        else:
            results['failed'] += 1
            results['detailed_results'].append({
                'route': route,
                'error': str(e)
            })
            print(f" ❌ ({str(e)[:30]})")
    except TimeoutError:
        results['failed'] += 1
        results['detailed_results'].append({
            'route': route,
            'error': 'Timeout'
        })
        print(f" ⏱️  (Timeout)")
    except Exception as e:
        results['failed'] += 1
        results['detailed_results'].append({
            'route': route,
            'error': str(e)
        })
        print(f" ❌ ({str(e)[:30]})")

# Generar reporte
print("\n" + "="*60)
print("REPORTE FINAL")
print("="*60 + "\n")

print(f"✓ Rutas exitosas: {results['passed']}")
print(f"✗ Rutas fallidas: {results['failed']}")
print(f"⚠️  Rutas con headings sin traducir: {len(results['untranslated_headers'])}\n")

if results['untranslated_headers']:
    print("="*60)
    print("RUTAS CON CLAVES SIN TRADUCIR")
    print("="*60 + "\n")
    
    for r in results['untranslated_headers']:
        print(f"📍 Ruta: {r['route']}")
        print(f"   Elementos sin traducir: {r['count']}")
        for item in r['items'][:5]:
            print(f"   - [{item['element']}] \"{item['text']}\"")
        if r['count'] > 5:
            print(f"   ... y {r['count'] - 5} más")
        print()

print("\n" + "="*60)
print("REPORTE DETALLADO")
print("="*60 + "\n")

for r in results['detailed_results']:
    if 'error' in r:
        print(f"❌ {r['route']}: {r['error']}")
    elif r.get('untranslated_count', 0) > 0:
        print(f"⚠️  {r['route']}: HTTP {r['status']} - {r['untranslated_count']} sin traducir de {r['headers_found']} headings")
    else:
        print(f"✅ {r['route']}: HTTP {r['status']} - OK ({r['headers_found']} headings)")

print("\n" + "="*60 + "\n")
