from django.db import migrations, models
from evap.evaluation.models import Infotext


def create_infotexts(apps, _schema_editor):
    infotext = apps.get_model("evaluation", "Infotext")

    infotexts = [
        (
            "Information for contributors",
            "Informationen für Mitwirkende",
            """<b>Delegates</b><br>
Lecturers can assign delegates to help them with the preparation of the evaluation.\n<a href="/profile">You can assign your own delegates on your profile page.</a><br>
Evaluations from lecturers who set you as a delegate are marked with a label below.<br>
<em>More details: <a href="/faq#faq-15-q">FAQ/Delegates</a></em><br>
<br>
<b>States of the evaluations</b><br>
You can only edit evaluations which are in the state "prepared". After you approved an evaluation it will automatically change to the state "editor approved" and your preparation is finished.<br>
<em>More details: <a href="/faq#faq-18-q">FAQ/States</a></em><br>
<br>
<b>Evaluation Results</b><br>
Text answers will be shown to the people who were evaluated and to the people responsible for the course. Voting answers will be published for all users of the platform if at least two people participated in the evaluation. The average grade is calculated if the participation rate is at least 20 percent.<br>
<em>More details: <a href="/faq#faq-3-s">FAQ/Results</a></em>""",
            """<b>Stellvertretende</b><br>
Lehrende können Stellvertretende definieren, die ihnen bei der Vorbereitung der Evaluierung helfen.\n<a href="/profile">Sie können Stellvertretende auf Ihrer Einstellungsseite definieren.</a><br>
Evaluierungen von Lehrenden, von denen Sie als Stellvertreter·in definiert wurden, sind unten mit einem Label markiert.<br>
<em>Mehr Infos: <a href="/faq#faq-15-q">FAQ/Stellvertretende</a></em><br>
<br>
<b>Zustand der Evaluierungen</b><br>
Sie können nur Evaluierungen im Zustand "vorbereitet" bearbeiten. Nachdem Sie eine Evaluierung bestätigt haben, wechselt diese automatisch in den Zustand "von Bearbeiter·in bestätigt" und Ihre Vorbereitung ist abgeschlossen.<br>
<em>Mehr Infos: <a href="/faq#faq-18-q">FAQ/Zustände</a></em><br>
<br>
<b>Evaluierungs-Ergebnisse</b><br>
Textantworten werden den bewerteten Personen und den Verantwortlichen der Veranstaltung angezeigt. Antworten auf Abstimmungsfragen werden für alle Nutzer·innen der Plattform veröffentlicht, wenn mindestens zwei Personen an der Evaluierung teilgenommen haben. Durchschnittsnoten werden berechnet, wenn die Teilnahmequote mindestens 20 Prozent beträgt.<br>
<em>Mehr Infos: <a href="/faq#faq-3-s">FAQ/Ergebnisse</a></em>""",
            Infotext.Page.CONTRIBUTOR_INDEX,
        ),
        (
            "Information about the evaluation",
            "Informationen zur Evaluierung",
            """<b>Anonymity</b><br>
Your votes and text answers can't be related to you. But you should be aware that your style of writing might allow lecturers to guess who wrote the text answer, especially in small courses.<br>
<em>More details: <a href="/faq#faq-21-q">FAQ/Anonymity</a></em><br>
<br>
<b>References to other answers</b><br>
Lecturers can't see completed questionnaires as a whole. If you would write "see above", the lecturer can't find the respective answer.<br>
<em>More details: <a href="/faq#faq-24-q">FAQ/Reference</a></em><br>
<br>
<b>Evaluation Results</b><br>
Text answers will be shown to the people who were evaluated and to the people responsible for the course. Voting answers will be published for all users of the platform if at least two people participated in the evaluation. The average grade is calculated if the participation rate is at least 20 percent.<br>
<em>More details: <a href="/faq#faq-3-s">FAQ/Results</a></em>""",
            """<b>Anonymität</b><br>
Deine abgegebenen Stimmen und Textantworten können dir technisch nicht zugeordnet werden. Dir sollte aber bewusst sein, dass dich Mitwirkende insbesondere in kleinen Veranstaltungen an deinem Schreibstil erkennen könnten.<br>
<em>Mehr Infos: <a href="/faq#faq-21-q">FAQ/Anonymität</a></em><br>
<br>
<b>Verweise auf andere Antworten</b><br>
Lehrende können sich keine kompletten Fragebögen ansehen. Wenn du in einer Textantwort schreibst "wie oben schon erwähnt", können sie die zugehörige Antwort nicht finden.<br>
<em>Mehr Infos: <a href="/faq#faq-24-q">FAQ/Verweise</a></em><br>
<br>
<b>Evaluierungs-Ergebnisse</b><br>
Textantworten werden den bewerteten Personen und den Verantwortlichen der Veranstaltung angezeigt. Antworten auf Abstimmungsfragen werden für alle Nutzer·innen der Plattform veröffentlicht, wenn mindestens zwei Personen an der Evaluierung teilgenommen haben. Durchschnittsnoten werden berechnet, wenn die Teilnahmequote mindestens 20 Prozent beträgt.<br>
<em>Mehr Infos: <a href="/faq#faq-3-s">FAQ/Ergebnisse</a></em>""",
            Infotext.Page.STUDENT_INDEX,
        ),
        ("", "", "", "", Infotext.Page.GRADES_PAGES),
    ]

    for title_en, title_de, content_en, content_de, page in infotexts:
        infotext.objects.create(title_en=title_en, title_de=title_de, content_en=content_en, content_de=content_de,
                                page=page)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0131_userprofile_ordering'),
    ]

    operations = [
        migrations.CreateModel(
            name='Infotext',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title_de', models.CharField(max_length=255, blank=True, verbose_name='title (german)')),
                ('title_en', models.CharField(max_length=255, blank=True, verbose_name='title (english)')),
                ('content_de', models.TextField(blank=True, verbose_name='content (german)')),
                ('content_en', models.TextField(blank=True, verbose_name='content (english)')),
                ('page', models.CharField(choices=[('student_index', 'Student index page'), ('contributor_index', 'Contributor index page'), ('grades_pages', 'Grade publishing pages')], max_length=30, unique=True, null=False, blank=False, verbose_name='page for the infotext to be visible on')),
            ],
            options={
                'verbose_name': 'infotext',
                'verbose_name_plural': 'infotexts',
            },
        ),
        migrations.AddConstraint(
            model_name="infotext",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("content_de", ""), ("content_en", ""), ("title_de", ""), ("title_en", "")),
                    models.Q(
                        models.Q(
                            ("content_de", ""), ("content_en", ""), ("title_de", ""), ("title_en", ""), _connector="OR"
                        ),
                        _negated=True,
                    ),
                    _connector="OR",
                ),
                name="infotexts_not_half_empty",
                violation_error_message="Please supply either all or no fields for this infotext.",
            ),
        ),
        migrations.RunPython(create_infotexts, reverse_code=lambda a, b: None)
    ]
