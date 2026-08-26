// Votes for one top.gg bot listing using one Discord account. Adapted from a
// script the user had working before (puppeteer-extra + stealth plugin to
// get past Cloudflare's bot check, plus injecting the Discord token directly
// into localStorage instead of driving the login form) - DrissionPage has no
// real equivalent to the stealth plugin, so this reuses the proven approach
// instead of trying to replicate it in Python.
//
// Input  (stdin, JSON): { "token": "...", "botId": "...", "chromePath": "...", "captchalyApiKey": "..." }
// Output (stdout, JSON): { "success": true, "message": "..." } or { "success": false, "message": "..." }

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

const delay = (ms) => new Promise((res) => setTimeout(res, ms));

async function solveTurnstile(page, captchalyApiKey) {
    if (!captchalyApiKey) return;

    const siteKey = await page.evaluate(() => {
        const cfDiv = document.querySelector('.cf-turnstile');
        if (cfDiv) return cfDiv.getAttribute('data-sitekey');
        const iframe = document.querySelector('iframe[src*="turnstile"]');
        if (iframe) {
            const match = iframe.src.match(/sitekey=([^&]+)/);
            if (match) return match[1];
        }
        return null;
    });
    if (!siteKey) return;

    try {
        const { CaptchalyClient } = require('captchaly');
        const client = new CaptchalyClient(captchalyApiKey);
        const result = await client.turnstile(page.url(), siteKey);

        await page.evaluate((t) => {
            const input = document.querySelector('[name="cf-turnstile-response"]');
            if (input) {
                input.value = t;
                const form = input.closest('form');
                if (form) form.submit();
            }
        }, result.token);
        await delay(5000);
    } catch (err) {
        process.stderr.write(`Captchaly turnstile solve failed: ${err.message}\n`);
    }
}

async function run({ token, botId, chromePath, captchalyApiKey }) {
    let browser;
    try {
        browser = await puppeteer.launch({
            headless: 'new',
            executablePath: chromePath,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--ignore-certificate-errors',
                '--disable-blink-features=AutomationControlled',
            ],
        });

        const page = await browser.newPage();
        await page.setViewport({ width: 1920, height: 1080 });
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

        const injectToken = (t) => {
            const formatted = t.startsWith('"') ? t : `"${t}"`;
            try { window.localStorage.setItem('token', formatted); } catch (e) {}
        };

        await page.evaluateOnNewDocument(injectToken, token);
        await page.goto('https://discord.com/channels/@me', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        await delay(4000);
        await page.evaluate(injectToken, token);

        await page.goto('https://top.gg/login', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        await delay(6000);
        await solveTurnstile(page, captchalyApiKey);

        if (page.url().includes('discord.com/oauth2')) {
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await delay(2000);
            await page.evaluate(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const scrollBtn = btns.find((b) => (b.innerText || '').toLowerCase().includes('keep scrolling'));
                if (scrollBtn) scrollBtn.click();
            });
            await delay(2000);
            const authClicked = await page.evaluate(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const authBtn = btns.find((b) => ['authorize', 'otorisasi', 'authorise'].includes((b.innerText || '').trim().toLowerCase()));
                if (authBtn) { authBtn.click(); return true; }
                return false;
            });
            if (authClicked) {
                await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
                await delay(4000);
            }
        }

        await page.goto(`https://top.gg/bot/${botId}/vote`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        await delay(15000);
        await solveTurnstile(page, captchalyApiKey);

        await page.evaluate(() => window.scrollBy(0, 800));
        await delay(2000);
        await page.evaluate(() => {
            const els = Array.from(document.querySelectorAll("button, a, [role='button']"));
            const agreeBtn = els.find((b) => (b.innerText || '').trim().toLowerCase() === 'agree');
            if (agreeBtn) agreeBtn.click();
        });
        await delay(3000);

        let btnData = { status: 'not_found' };
        for (let attempt = 1; attempt <= 8; attempt++) {
            btnData = await page.evaluate(() => {
                const bodyText = document.body.innerText.toLowerCase();
                if (bodyText.includes('already voted')) return { status: 'already' };
                const btns = Array.from(document.querySelectorAll("button, a, [role='button']"));
                const voteBtn = btns.find((el) => ['vote', 'vote!', 'vote for bot'].includes((el.innerText || '').trim().toLowerCase()));
                if (voteBtn && !voteBtn.disabled) {
                    voteBtn.scrollIntoView({ block: 'center', behavior: 'instant' });
                    const rect = voteBtn.getBoundingClientRect();
                    return { status: 'found', x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
                }
                return { status: 'not_found' };
            });
            if (btnData.status !== 'not_found') break;
            await delay(5000);
        }

        if (btnData.status === 'already') {
            return { success: true, message: 'Already voted' };
        }
        if (btnData.status !== 'found') {
            return { success: false, message: 'Vote button never appeared (timed out)' };
        }

        await delay(1500);
        await page.mouse.click(btnData.x, btnData.y);
        await delay(3000);
        await solveTurnstile(page, captchalyApiKey);
        await delay(6000);

        const isSuccess = await page.evaluate(() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes('thank you for voting') || text.includes('thanks for voting') || text.includes('already voted') || text.includes('successfully voted');
        });

        return isSuccess
            ? { success: true, message: 'Voted successfully' }
            : { success: false, message: 'Clicked vote but server did not confirm it' };
    } finally {
        if (browser) await browser.close();
    }
}

let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', async () => {
    try {
        const params = JSON.parse(input);
        const result = await run(params);
        process.stdout.write(JSON.stringify(result));
    } catch (error) {
        process.stdout.write(JSON.stringify({ success: false, message: error && error.message ? error.message : String(error) }));
        process.exitCode = 1;
    }
});

