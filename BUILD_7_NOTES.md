# Samuga Media Build 7

## What changed

- English public and dashboard typography now uses Poppins.
- Dhivehi editorial text uses MV Faseyha with Noto Sans Thaana and Faruma fallbacks.
- No font file is bundled in this project; the webfont is requested externally.
- All public and dashboard CSS/JS filenames are unique to Build 7, preventing old cached Build 5/6 JavaScript from being mixed with new HTML.
- The Ask Samuga AI launcher always retains its full label on mobile.
- The Samuga AI profile mark is present in both the launcher and chat header.
- Mobile chat uses Visual Viewport sizing, does not automatically open the keyboard, and remains inside the visible screen when the keyboard is shown.
- Content Lab navigation uses delegated clicks and a direct #contentlab route.
- Content Lab failures are shown inside the dashboard with a retry control rather than only as a disappearing toast.
- The backend Content Lab endpoint reports Build 7 and confirms that it uses the existing shared approval queue.

## Safe deployment order

1. Deploy `Samuga-News-Bot-Build-7-Content-Lab-Diagnostics.zip` to Railway.
2. Confirm the bot is healthy and Telegram Content Lab is still operating.
3. Deploy `Samuga-Media-Build-7-Typography-AI-Content-Lab.zip` to Cloudflare Pages.
4. Open `/admin#contentlab` and test one disposable card.
5. Check the public AI button and chat on a real iPhone/Android device.

No existing publishing route or Telegram approval action was removed.
