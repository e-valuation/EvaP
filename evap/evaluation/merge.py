from django.db import transaction
from django.db.models import Model
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey

# based on https://djangosnippets.org/snippets/2283/


@transaction.atomic
def merge_model_objects(primary_object, alias_objects, keep_old=False):
    """
    Use this function to merge model objects (i.e. Users, Organizations, Polls,
    etc.) and migrate all of the related fields from the alias objects to the
    primary object.

    Usage:
    from evap.evaluation.models import UserProfile
    primary_user = UserProfile.objects.get(email='good_email@example.com')
    duplicate_user = UserProfile.objects.get(email='good_email+duplicate@example.com')
    merge_model_objects(primary_user, duplicate_user)
    """
    if not isinstance(alias_objects, list):
        alias_objects = [alias_objects]

    # check that all aliases are the same class as primary one and that
    # they are subclass of model
    primary_class = primary_object.__class__

    if not issubclass(primary_class, Model):
        raise TypeError('Only django.db.models.Model subclasses can be merged')

    for alias_object in alias_objects:
        if not isinstance(alias_object, primary_class):
            raise TypeError('Only models of same class can be merged')

    # Get a list of all GenericForeignKeys in all models
    # TODO: this is a bit of a hack, since the generics framework should provide a similar
    # method to the ForeignKey field for accessing the generic related fields.
    generic_fields = []
    for model in apps.get_models():
        for field_name, field in [x for x in model.__dict__.items() if isinstance(x[1], GenericForeignKey)]:
            generic_fields.append(field)

    blank_local_fields = set([field.attname for field in primary_object._meta.local_fields if getattr(primary_object, field.attname) in [None, '']])

    # Loop through all alias objects and migrate their data to the primary object.
    for alias_object in alias_objects:
        # Migrate all foreign key references from alias object to primary object.
        for related_field in alias_object._meta.get_fields():
            if not ((related_field.one_to_many or related_field.one_to_one) and related_field.auto_created):
                continue
            # The variable name on the alias_object model.
            alias_varname = related_field.get_accessor_name()

            # The variable name on the related model.
            obj_varname = related_field.field.name
            related_fields = getattr(alias_object, alias_varname)

            if hasattr(related_fields, 'all'):
                for obj in related_fields.all():
                    setattr(obj, obj_varname, primary_object)
                    obj.save()

        # Migrate all many to many references from alias object to primary object.
        for related_many_field in alias_object._meta.get_fields(include_hidden=True):
            if not (related_many_field.many_to_many and related_many_field.auto_created):
                continue
            alias_varname = related_many_field.get_accessor_name()
            obj_varname = related_many_field.field.name

            if alias_varname != "+" and alias_varname[-1] != "+":
                if alias_varname is not None:
                    # standard case
                    related_many_fields = getattr(alias_object, alias_varname).all()
                else:
                    # special case, symmetrical relation, no reverse accessor
                    related_many_fields = getattr(alias_object, obj_varname).all()
                for obj in related_many_fields.all():
                    getattr(obj, obj_varname).remove(alias_object)
                    getattr(obj, obj_varname).add(primary_object)

        # Migrate all generic foreign key references from alias object to primary object.
        for field in generic_fields:
            filter_kwargs = {}
            filter_kwargs[field.fk_field] = alias_object._get_pk_val()
            filter_kwargs[field.ct_field] = field.get_content_type(alias_object)
            for generic_related_field in field.model.objects.filter(**filter_kwargs):
                setattr(generic_related_field, field.name, primary_object)
                generic_related_field.save()

        # Try to fill all missing values in primary object by values of duplicates
        filled_up = set()
        for field_name in blank_local_fields:
            val = getattr(alias_object, field_name)
            if val not in [None, '']:
                setattr(primary_object, field_name, val)
                filled_up.add(field_name)
        blank_local_fields -= filled_up

        if not keep_old:
            alias_object.delete()
    primary_object.save()
    return primary_object
