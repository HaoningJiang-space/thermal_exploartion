"""Retired and current same-named evidence must never overwrite one another."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


class RawPackageTests(unittest.TestCase):
    def test_same_case_under_distinct_sources_is_preserved(self):
        script=Path(__file__).resolve().parents[1]/'scripts/package_expert_raw.py'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); sources=[]
            for name in ('retired', 'fixed'):
                source=root/name/'same-case';source.mkdir(parents=True)
                (source/'result.json').write_text(json.dumps({'source':name}))
                sources.append(str(source))
            output=root/'evidence'
            subprocess.run([sys.executable,str(script),'--sources',*sources,
                            '--output',str(output),'--name','test'],check=True,
                           stdout=subprocess.PIPE,text=True)
            manifest=json.loads((output/'raw-manifest.json').read_text())
            self.assertEqual(len({r['file'] for r in manifest}),2)
            for record in manifest:
                data=(output/'entries'/record['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
                with tarfile.open(output/'entries'/record['file']) as archive:
                    entry=archive.next()
                    result=json.load(archive.extractfile(entry))
                    self.assertTrue(entry.name.startswith(result['source']+'-same-case/'))
