import csv
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import job_applicant as app
from resume_match import read_resume, rank, tokens


class SearchTests(unittest.TestCase):
    def test_phrase_matching_preserves_source_boundaries(self):
        for value in ("Data\nEducation\nEngineer", "Data. Engineer", "Data and Engineer", "Data 2025 Engineer"):
            with self.subTest(value=value):
                self.assertNotIn("data engineer", tokens(value))
        self.assertIn("data engineer", tokens("Experienced data engineer"))
        self.assertIn("c++ robotics", tokens("C++ robotics"))

    def test_ranking_changes_with_resume(self):
        jobs = [{"title": "Technician", "company": "A", "description": "Pipetting and microscopy"},
                {"title": "Technician", "company": "B", "description": "C++ robotics and PLC"}]
        rank(jobs, "PLC robotics C++")
        self.assertEqual(jobs[0]["company"], "B")
        self.assertIn("c++", jobs[0]["matched_terms"])
        rank(jobs, "Pipetting microscopy")
        self.assertEqual(jobs[0]["company"], "A")
        self.assertEqual(jobs[1]["resume_score"], 0)

    def test_docx_reads_split_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"r.docx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Micro</w:t></w:r><w:r><w:t>scopy</w:t></w:r></w:p></w:document>')
            self.assertEqual(read_resume(path), "Microscopy")

    def test_empty_pdf(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"r.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(path)
            with self.assertRaisesRegex(ValueError, 'No readable text'):
                read_resume(path)

    def test_pdf_text(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"r.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=400, height=400)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 20 20 Td (Robotics Technician) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
            writer.write(path)
            self.assertIn("Robotics Technician", read_resume(path))

    def test_new_user_interactive_then_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/"resume.txt").write_text("Pipetting and microscopy")
            settings = dict(app.SOURCES, public_sources=[], direct_jobs=[
                {"title": title, "company": "Sample", "location": city,
                 "description": desc, "url": f"https://example.com/job?id={idx}"}
                for idx, (title, city, desc) in enumerate([
                    ("Lab Technician", "Paris", "filing"), ("Lab Technician", "Paris", "pipetting"),
                    ("Lead Lab Technician", "Paris", "pipetting"), ("Lab Technician", "Rome", "pipetting"),
                    ("Accountant", "Paris", "pipetting")])])
            app.save_json(folder/"sources.json", settings)
            command = [sys.executable, str(Path(app.__file__).resolve())]
            subprocess.run(command, input="lab technician\nParis\nlead\nresume.txt\n",
                           cwd=folder, text=True, capture_output=True, check=True)
            subprocess.run(command+["search", "--batch"], cwd=folder, capture_output=True, check=True)
            payload = json.loads((folder/"jobs.json").read_text())
            self.assertEqual(payload["diagnostics"]["collected_unique"], 5)
            self.assertEqual(payload["diagnostics"]["after_title_filter"], 4)
            self.assertEqual(payload["diagnostics"]["after_location_filter"], 3)
            self.assertEqual(payload["diagnostics"]["after_exclusions"], 2)
            rows = payload["jobs"]
            self.assertEqual([r["description"] for r in rows], ["pipetting", "filing"])
            with (folder/"jobs.csv").open(encoding="utf-8-sig") as f:
                self.assertEqual(list(csv.DictReader(f))[0]["matched_terms"], "pipetting")

    def test_himalayas_sends_role_only_and_skips_expired(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return {"jobs": [{"expiryDate": 1}, {"title": "Designer", "companyName": "Sample",
                             "description": "typography", "applicationLink": "https://example.com/apply",
                             "guid": "https://himalayas.app/companies/example/jobs/example"}]}
        jobs = app.public_jobs("himalayas", "designer", fetch)
        self.assertEqual(len(jobs), 1)
        self.assertIn("q=designer&page=1", urls[0])
        self.assertIn("Worldwide", jobs[0]["location"])
