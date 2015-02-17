from django_webtest import WebTest

class UsecaseTests(WebTest):
    fixtures = ['minimal_test_data_results']

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='responsible')
        self.assertIn(".orig_published.", page)
        self.assertNotIn(".orig_not_published.", page)
        self.assertNotIn(".orig.", page)
        self.assertIn(".changed.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_not_published.", page)
        self.assertNotIn(".responsible_orig.", page)
        self.assertIn(".responsible_changed.", page)
        self.assertIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_unchecked.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page) # private comment not visible

    def test_textanswer_visibility_for_delegate_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_responsible')
        self.assertIn(".orig_published.", page)
        self.assertNotIn(".orig_not_published.", page)
        self.assertNotIn(".orig.", page)
        self.assertIn(".changed.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_not_published.", page)
        self.assertNotIn(".responsible_orig.", page)
        self.assertIn(".responsible_changed.", page)
        self.assertNotIn(".responsible_orig_private.", page) # private comment not visible
        self.assertNotIn(".responsible_orig_unchecked.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page) # private comment not visible

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor')
        self.assertNotIn(".orig_published.", page)
        self.assertNotIn(".orig_not_published.", page)
        self.assertNotIn(".orig.", page)
        self.assertNotIn(".changed.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_not_published.", page)
        self.assertNotIn(".responsible_orig.", page)
        self.assertNotIn(".responsible_changed.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_unchecked.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_delegate_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_contributor')
        self.assertNotIn(".orig_published.", page)
        self.assertNotIn(".orig_not_published.", page)
        self.assertNotIn(".orig.", page)
        self.assertNotIn(".changed.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_not_published.", page)
        self.assertNotIn(".responsible_orig.", page)
        self.assertNotIn(".responsible_changed.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_unchecked.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/course/1", user='student')
        self.assertNotIn(".orig_published.", page)
        self.assertNotIn(".orig_not_published.", page)
        self.assertNotIn(".orig.", page)
        self.assertNotIn(".changed.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_not_published.", page)
        self.assertNotIn(".responsible_orig.", page)
        self.assertNotIn(".responsible_changed.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_unchecked.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
