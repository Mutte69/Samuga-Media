# Samuga Media Build 8

Build 8 is based on Build 7. It preserves the existing typography, Content Lab, author identity, video newsroom, publishing queue, light/dark mode and dashboard permissions.

## Public article fixes

- Dhivehi detection now accepts lowercase/uppercase language values and also detects Thaana script.
- Only the article content switches to RTL. The site header, share controls and browser layout remain stable in LTR.
- Dhivehi headlines, subheadlines, paragraphs, captions and related-story titles use explicit RTL direction, normal letter spacing and safe wrapping.
- Single line breaks inside a paragraph are preserved safely.
- Related and share labels have Dhivehi variants.
- English article rendering is unchanged.

## Samuga AI mobile chat fixes

- The chat panel and input controls no longer inherit the website's RTL direction.
- The close button remains on the right and the Send button remains on the right.
- The panel width is calculated from `visualViewport.width`, fixing clipping in Telegram's iPhone browser.
- The panel height and position adapt when the iOS keyboard opens.
- The closed-keyboard panel uses a shorter bottom-sheet layout instead of filling the whole screen with empty space.
- Messages use automatic text direction, allowing English and Thaana inside the same chat.

## Article cover editing

The article editor now provides:

- Replace file
- Remove cover
- Choose another item from the Media Library
- Add Samuga branding

Removing a cover removes it only from the current article. The original uploaded file remains in the Media Library, where an administrator can delete it separately when it is no longer needed.

## Dashboard branding

`Add Samuga branding` calls a protected newsroom endpoint and uses the same `generate_web_cover()` function used by the Telegram `/article` cover workflow. It creates a new 1200×630 branded copy with:

- Samuga Media logo
- Category label
- Samuga Media footer strip
- `samugamedia.com`

The original image is preserved.

## Deployment order

1. Deploy `Samuga-News-Bot-Build-8-Branded-Cover-Backend.zip` to Railway.
2. Confirm Railway starts successfully.
3. Deploy `Samuga-Media-Build-8-Dhivehi-Chat-Branded-Covers.zip` to Cloudflare Pages.
4. Hard-refresh the website and dashboard.
5. Test one Dhivehi article, the mobile chat inside Telegram, and one disposable branded cover.

No new environment variables are required.
