# Samuga Media Website — Build 5

## Author identity

- Added a dedicated **Authors** section to the newsroom dashboard.
- Authors can edit their public name, profile photo and bio.
- Administrators can edit public roles, Telegram IDs and active status.
- Newsroom user accounts can be linked directly to an existing Telegram author profile.
- The author selector identifies Telegram, dashboard and Samuga AI profiles.
- This prevents a dashboard login and Telegram account from appearing as two different public authors.

## Article deletion

- Super Admins now have a permanent **Delete article** action in the article list and editor.
- Other roles never receive the delete control.

## Dhivehi typography

- Replaced Noto Sans Thaana as the primary face with **Faruma Regular** loaded as an external webfont.
- No font file is bundled in the repository.
- Reduced Dhivehi headline size, removed synthetic heavy weights and increased reading line-height.
- Applied the same Thaana typography to the public website, dashboard editor and preview.

## Deploy

Deploy this website only after the matching Build 5 backend is live on Railway.
