#!/usr/bin/env python3
"""
Smoke test completo con barrido automático de claves sin traducir.
"""

import asyncio
import re
import sys
from playwright.async_api import async_playwright

async def run_smoke_test():
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
        '/capacity-planning',
        '/billing-reports',
        '/approvals',
        '/alerts',
        '/absences'
    ]

    results = {
        'passed': 0,
        'failed': 0,
        'untranslated_headers': [],
        'detailed_results': []
    }

    # Patrón para detectar claves sin traducir
    untranslated_pattern = re.compile(r'^(title|subtitle|[a-z_]+\.[a-z_]+)$', re.IGNORECASE)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.create_context()
        page = await context.new_page()

        for route in routes:
            try:
                url = f"http://localhost:3000{route}"
                print(f"Testing {route}...", end='', flush=True)

                response = await page.goto(url, wait_until='networkidle', timeout=15000)

                if response and response.status >= 400:
                    results['failed'] += 1
                    results['detailed_results'].append({
                        'route': route,
                        'status': response.status,
                        'error': f"HTTP {response.status}"
                    })
                    print(f" ❌ ({response.status})")
                    continue

                # Esperar a que React renderice
                await page.wait_for_timeout(1000)

                # Inspeccionar headings
                headers_data = await page.evaluate("""
                    () => {
                        const headers = [];
                        const selectors = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', '[class*="title"]', '[class*="subtitle"]'];
                        const seen = new Set();

                        selectors.forEach(selector => {
                            try {
                                document.querySelectorAll(selector).forEach(el => {
                                    const text = el.textContent?.trim();
                                    if (text && text.length > 0 && text.length < 200) {
                                        const key = `${el.tagName}-${text}`;
                                        if (!seen.has(key)) {
                                            seen.add(key);
                                            headers.push({
                                                element: el.tagName.toLowerCase(),
                                                class: el.className,
                                                text: text
                                            });
                                        }
                                    }
                                });
                            } catch (e) {}
                        });

                        return headers;
                    }
                """)

                # Filtrar headings sin traducir
                untranslated = []
                for h in headers_data:
                    text = h['text'].lower()
                    if (untranslated_pattern.match(text) or
                        'title' in text or
                        'subtitle' in text or
                        re.match(r'^[a-z_]+\.[a-z_]+$', text)):
                        untranslated.append(h)

                results['passed'] += 1

                if untranslated:
                    results['untranslated_headers'].append({
                        'route': route,
                        'count': len(untranslated),
                        'items': untranslated
                    })

                results['detailed_results'].append({
                    'route': route,
                    'status': response.status if response else 200,
                    'headers_found': len(headers_data),
                    'untranslated_count': len(untranslated),
                    'untranslated': untranslated
                })

                if untranslated:
                    print(f" ⚠️  ({len(untranslated)} sin traducir)")
                else:
                    print(" ✅")

            except asyncio.TimeoutError:
                results['failed'] += 1
                results['detailed_results'].append({
                    'route': route,
                    'error': 'Timeout'
                })
                print(" ⏱️ (Timeout)")
            except Exception as e:
                results['failed'] += 1
                results['detailed_results'].append({
                    'route': route,
                    'error': str(e)
                })
                print(f" ❌ ({str(e)[:30]})")

        await context.close()
        await browser.close()

    # Generar reporte
    print("\n" + "="*50)
    print("SMOKE TEST COMPLETO - REPORTE FINAL")
    print("="*50 + "\n")

    print(f"✓ Rutas exitosas: {results['passed']}")
    print(f"✗ Rutas fallidas: {results['failed']}")
    print(f"⚠️  Rutas con headings sin traducir: {len(results['untranslated_headers'])}\n")

    if results['untranslated_headers']:
        print("="*50)
        print("RUTAS CON CLAVES SIN TRADUCIR")
        print("="*50 + "\n")

        for r in results['untranslated_headers']:
            print(f"📍 Ruta: {r['route']}")
            print(f"   Elementos sin traducir: {r['count']}")
            for item in r['items'][:5]:
                print(f"   - [{item['element']}] \"{item['text']}\"")
            if r['count'] > 5:
                print(f"   ... y {r['count'] - 5} más")
            print()

    print("\n" + "="*50)
    print("REPORTE DETALLADO POR RUTA")
    print("="*50 + "\n")

    for r in results['detailed_results']:
        if 'error' in r:
            print(f"❌ {r['route']}: {r['error']}")
        elif r.get('untranslated_count', 0) > 0:
            print(f"⚠️  {r['route']}: HTTP {r['status']} - {r['untranslated_count']} claves sin traducir de {r['headers_found']} headings")
        else:
            print(f"✅ {r['route']}: HTTP {r['status']} - OK ({r['headers_found']} headings)")

    return results

if __name__ == '__main__':
    results = asyncio.run(run_smoke_test())
    sys.exit(0 if results['failed'] == 0 else 1)
