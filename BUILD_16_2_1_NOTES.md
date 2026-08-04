# Samuga Media Build 16.2.1 — Emergency UI Repair

## Root causes found
- The page-entry animation permanently retained a transformed `body`, so `position: fixed` controls were positioned against document height instead of the viewport. This is why the AI button appeared attached to the footer or vanished while scrolling.
- `overflow-x: hidden` on `html/body` created the wrong sticky containing block, so the header still scrolled away.
- The featured media grid item stretched to the height of the long headline while its inner media did not fill that height, creating the large blank panel.
- Website Settings replaced the branded header background with the page background in light mode, making the white logo and controls nearly invisible.
- Two separate chat binders and a standalone AI route created conflicting behavior.

## Corrected
- Removed the standalone `/ask-samuga-ai` page and all public links to it.
- Sidebar and floating Ask Samuga AI controls now open the same smooth overlay chat.
- Consolidated public chat binding into one controller to remove duplicate event/state logic.
- Repaired floating button visibility defaults while preserving the new `ai_enabled` admin control.
- Restored the solid Samuga blue sticky header in light and dark themes.
- Fixed the featured media blank area by giving the media a fixed aspect ratio and making its content fill the frame.
- Rebuilt the mobile hero as a simple block layout with readable headline sizing and no broken word wrapping.
- Changed mobile AI from a forced full-screen panel to a compact bottom sheet, with keyboard-aware resizing.

## Deployment
Deploy the contents of this folder to Cloudflare Pages. No database migration is required for these fixes.
