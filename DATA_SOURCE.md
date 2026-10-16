# Data source and permissions

Source: https://rebrickable.com/downloads/

The following data-use statement was recorded from the Downloads page on October 14, 2026:

> Free for personal and commercial use, provided you acknowledge Rebrickable as your data source.

The same statement limits automated archive downloads to at most once a day and prohibits scraping Rebrickable web pages. This project does neither: it imports the supplied CSV snapshot and uses the bundled database at runtime. Rebrickable is acknowledged in the interface and README.

The app displays set-image URLs supplied with the catalog. Original image files are served from their source CDN rather than bundled with the application. The README includes a screenshot of the interface using a built-in example collection. Instruction links open LEGO's official website; PDFs are not hosted by this project. Data permissions do not transfer ownership of LEGO trademarks or third-party images.

`data/catalog_info.json` records input file fingerprints and the generated archive checksum. Future refreshes must recheck the then-current terms and respect the download frequency limit.
