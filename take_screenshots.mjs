/**
 * Automated screenshot capture for Car Carer README.
 * Prerequisites: server running on 127.0.0.1:8200 with demo data seeded.
 */

import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const BASE = 'http://127.0.0.1:8200';
const OUT = 'docs/screenshots';
const VIEWPORT = { width: 1280, height: 800 };

mkdirSync(OUT, { recursive: true });

async function run() {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: VIEWPORT });
    const page = await context.newPage();

    // Helper: execute code on Alpine data
    async function alpineExec(code) {
        return await page.evaluate((c) => {
            const el = document.querySelector('[x-data]');
            if (!el) return 'no [x-data]';
            // Alpine v3: Alpine.$data(el) or el._x_dataStack[0]
            let data;
            if (window.Alpine && typeof window.Alpine.$data === 'function') {
                data = window.Alpine.$data(el);
            } else if (el._x_dataStack) {
                data = el._x_dataStack[0];
            }
            if (!data) return 'no data';
            try {
                const fn = new Function('data', c);
                fn(data);
                return 'ok';
            } catch (e) {
                return 'error: ' + e.message;
            }
        }, code);
    }

    // ── Login ──
    console.log('Logging in...');
    await page.goto(BASE);
    await page.waitForTimeout(2000);
    await page.fill('input[type="email"]', 'demo@carcarer.app');
    await page.fill('input[type="password"]', 'demo123456');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);

    // ── 1. Dashboard ──
    console.log('1/6 Dashboard...');
    let r = await alpineExec(`data.view = 'dashboard'`);
    console.log('    alpine:', r);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${OUT}/dashboard.png` });
    console.log('    ✓ dashboard.png');

    // ── Go to Vehicles + Select Peugeot 308 ──
    console.log('Selecting Peugeot 308...');
    r = await alpineExec(`data.view = 'vehicles'`);
    console.log('    alpine view:', r);
    await page.waitForTimeout(1500);

    r = await alpineExec(`
        const p = data.vehicles.find(v => v.name && v.name.includes('Peugeot'));
        if (p) { data.selectVehicle(p); return; }
        if (data.vehicles.length > 0) data.selectVehicle(data.vehicles[0]);
    `);
    console.log('    alpine select:', r);
    await page.waitForTimeout(3000);

    // Scroll to vehicle detail panel (find the detail heading)
    async function scrollToDetail() {
        await page.evaluate(() => {
            // Find the element showing the selected vehicle name in the detail panel
            const els = [...document.querySelectorAll('h2, h3, p')];
            const detail = els.find(el => el.textContent.includes('Peugeot 308') && el.offsetParent && el.getBoundingClientRect().y > 400);
            if (detail) {
                detail.scrollIntoView({ block: 'start', behavior: 'instant' });
                window.scrollBy(0, -60); // offset for header
            } else {
                window.scrollTo(0, 400); // fallback: scroll past the vehicle grid
            }
        });
        await page.waitForTimeout(300);
    }
    await scrollToDetail();

    // ── 2. Documents tab ──
    console.log('2/6 Documents tab...');
    r = await alpineExec(`data.detailTab = 'documents'`);
    console.log('    alpine:', r);
    await page.waitForTimeout(1500);
    // Scroll to show the detail panel fully
    await scrollToDetail();
    await page.screenshot({ path: `${OUT}/upload.png` });
    console.log('    ✓ upload.png');

    // ── 3. Fuel tab ──
    console.log('3/6 Fuel tab...');
    r = await alpineExec(`data.detailTab = 'fuel'; data.loadFuel()`);
    console.log('    alpine:', r);
    await page.waitForTimeout(3000);
    await scrollToDetail();
    await page.screenshot({ path: `${OUT}/fuel.png` });
    console.log('    ✓ fuel.png');

    // ── 4. Taxes tab ──
    console.log('4/6 Taxes tab...');
    r = await alpineExec(`data.detailTab = 'tax'; data.loadTaxInsurance()`);
    console.log('    alpine:', r);
    await page.waitForTimeout(2000);
    await scrollToDetail();
    await page.screenshot({ path: `${OUT}/taxes.png` });
    console.log('    ✓ taxes.png');

    // ── 5. Sharing tab ──
    console.log('5/6 Sharing tab...');
    r = await alpineExec(`data.detailTab = 'sharing'; data.loadAccess()`);
    console.log('    alpine:', r);
    await page.waitForTimeout(2000);
    await scrollToDetail();
    await page.screenshot({ path: `${OUT}/sharing.png` });
    console.log('    ✓ sharing.png');

    // ── 6. Chat ──
    console.log('6/6 Chat...');
    r = await alpineExec(`data.view = 'chat'`);
    console.log('    alpine:', r);
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.scrollTo(0, 0));
    try {
        const input = page.locator('input[type="text"]').last();
        if (await input.count() > 0) {
            await input.fill('Quand ai-je fait la derniere vidange de la Peugeot 308 ?');
        }
    } catch {}
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/chat.png` });
    console.log('    ✓ chat.png');

    await browser.close();
    console.log('\nDone! Screenshots in docs/screenshots/');
}

run().catch(e => {
    console.error('Error:', e.message);
    process.exit(1);
});
