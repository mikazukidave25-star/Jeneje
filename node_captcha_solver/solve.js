#!/usr/bin/env node
// Solves a single hCaptcha challenge using the official Captchaly SDK (npm
// package "captchaly"), then prints the result as JSON on stdout. Meant to be
// invoked as a short-lived subprocess from Python (see oauth.py's
// CaptchalyBridge), since no verified native Python client for Captchaly
// exists - this reuses the same SDK/call pattern already confirmed working
// in the companion TypeScript bot, instead of guessing the raw HTTP API.
//
// Input  (stdin, JSON): { "apiKey": "...", "sitekey": "...", "siteurl": "..." }
// Output (stdout, JSON): { "token": "..." } on success, { "error": "..." } on failure.

const { CaptchalyClient } = require("captchaly");

let input = "";
process.stdin.on("data", (chunk) => {
    input += chunk;
});

process.stdin.on("end", async () => {
    try {
        const { apiKey, sitekey, siteurl } = JSON.parse(input);
        if (!apiKey || !sitekey || !siteurl) {
            throw new Error("Missing apiKey, sitekey, or siteurl in input");
        }

        const client = new CaptchalyClient(apiKey);
        // Argument order/return shape matches the working CaptchalySolver.ts
        // integration: client.hcaptcha(siteurl, sitekey) -> { token }.
        const result = await client.hcaptcha(siteurl, sitekey);

        process.stdout.write(JSON.stringify({ token: result.token }));
    } catch (error) {
        process.stdout.write(JSON.stringify({ error: error && error.message ? error.message : String(error) }));
        process.exitCode = 1;
    }
});
