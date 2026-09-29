import json
import subprocess
from pathlib import Path
from PIL import Image
from django.test import TestCase, Client
from django.conf import settings


class PWAFoundationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.base_dir = Path(settings.BASE_DIR)

    def test_manifest_validity_and_installability(self):
        """
        Verify static/manifest.json is valid JSON and satisfies all
        W3C Web App Manifest baseline installability requirements:
        - name, short_name
        - start_url, scope, display: 'standalone'
        - theme_color, background_color
        - 192x192 and 512x512 icons that exist and have exact dimensions
        """
        manifest_path = self.base_dir / 'static' / 'manifest.json'
        self.assertTrue(manifest_path.exists(), "static/manifest.json does not exist")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # Baseline installability properties
        self.assertTrue(manifest.get('name'), "manifest missing 'name'")
        self.assertTrue(manifest.get('short_name'), "manifest missing 'short_name'")
        self.assertEqual(manifest.get('start_url'), '/')
        self.assertEqual(manifest.get('scope'), '/')
        self.assertEqual(manifest.get('display'), 'standalone')
        self.assertTrue(manifest.get('theme_color'), "manifest missing 'theme_color'")
        self.assertTrue(manifest.get('background_color'), "manifest missing 'background_color'")

        # Icons audit
        icons = manifest.get('icons', [])
        self.assertGreaterEqual(len(icons), 2, "manifest must contain at least 192 and 512 icons")

        sizes = {icon.get('sizes'): icon.get('src') for icon in icons}
        self.assertIn('192x192', sizes, "manifest missing 192x192 icon")
        self.assertIn('512x512', sizes, "manifest missing 512x512 icon")

        # Verify icon image files on disk
        icon_192_path = self.base_dir / sizes['192x192'].lstrip('/')
        icon_512_path = self.base_dir / sizes['512x512'].lstrip('/')
        self.assertTrue(icon_192_path.exists(), f"192 icon missing at {icon_192_path}")
        self.assertTrue(icon_512_path.exists(), f"512 icon missing at {icon_512_path}")

        # Check actual dimensions with PIL
        with Image.open(icon_192_path) as img:
            self.assertEqual(img.size, (192, 192), "192 icon dimension mismatch")
        with Image.open(icon_512_path) as img:
            self.assertEqual(img.size, (512, 512), "512 icon dimension mismatch")

    def test_service_worker_endpoint_and_headers(self):
        """
        Service worker must be served from the root URL '/service-worker.js'
        with Service-Worker-Allowed header set to '/' for whole-site scope.
        """
        res = self.client.get('/service-worker.js')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/javascript')
        self.assertEqual(res.get('Service-Worker-Allowed'), '/')

        content = res.content.decode('utf-8')
        # Check Workbox import
        self.assertIn('workbox-sw.js', content)
        # Check precache items
        self.assertIn('/offline/', content)
        self.assertIn('/static/css/style.css', content)
        self.assertIn('offline-sync.js', content)
        self.assertIn('image-compress.js', content)
        # Check sync tag listener
        self.assertIn('sync-outbox', content)

    def test_offline_page_rendering(self):
        """Offline fallback page must render with HTTP 200 and offline instructions."""
        res = self.client.get('/offline/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('Offline', content)
        self.assertIn('Soteria', content)

    def test_sync_issues_page_rendering(self):
        """Client-side Sync Issues page must render with HTTP 200."""
        res = self.client.get('/sync-issues/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('Sync Issues', content)
        self.assertIn('Offline Outbox', content)

    def test_base_template_pwa_head_and_scripts(self):
        """
        The base layout must include manifest link, apple-touch-icon,
        service worker registration, and PWA offline script tags.
        """
        res = self.client.get('/login/')
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        self.assertIn('rel="manifest"', html)
        self.assertIn('manifest.json', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('name="theme-color"', html)
        self.assertIn('service-worker.js', html)
        self.assertIn('offline-sync.js', html)
        self.assertIn('image-compress.js', html)
        self.assertIn('sync-ui.js', html)

    def test_node_offline_sync_and_image_compress_unit_tests(self):
        """Run Node.js unit tests for offline sync queue/replay and image compression."""
        test_file = self.base_dir / 'static' / 'js' / 'offline-sync.test.mjs'
        result = subprocess.run(
            ['node', '--test', str(test_file)],
            cwd=str(self.base_dir),
            capture_output=True,
            text=True
        )
        self.assertEqual(
            result.returncode, 0,
            f"Node JS unit tests failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
