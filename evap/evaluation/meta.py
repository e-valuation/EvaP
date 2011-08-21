from django.db.models.base import ModelBase
from django.utils.translation import get_language

Translate = object()

class LocalizeModelBase(ModelBase):
    """This meta-class provides automatically translated content properties. Set
    a model field to `Translate` and it will automatically return the property
    with the name of the current language. E.g. if there is a normal member
    `text_de`, a member `text = Translate` and the current language is `de`, then
    an object will return the content of `text_de` when it is asked for the value
    of `text`.
    """
    def __new__(metacls, classname, bases, classDict):
        # find all classDict entries that point to `Translate`
        for key in classDict.keys():
            if classDict[key] is Translate:
                # replace them with a getter that uses the current language
                def make_property(k):
                    return property(lambda self: getattr(self, "%s_%s" % (k, get_language())))
                classDict[key] = make_property(key)
        return super(LocalizeModelBase, metacls).__new__(metacls, classname, bases, classDict)
