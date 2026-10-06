# Separate file because we cannot have django imports here as the initialize_baker_seed method will run before
# django.setup() was called on the workers


class SeedBakerMixin:
    BAKER_SEED: int

    @classmethod
    def setUpClass(cls):
        # runs before `setUpTestData`
        from model_bakery import baker

        baker.seed(cls.BAKER_SEED)
        super().setUpClass()

    @classmethod
    def _pre_setup(cls):
        # runs before `setUp`
        # Same seed would imply the same value sequence, which causes problems:
        # * uniqueness constraints fail if setUpTestData and setUp both generate an instance of the same model class
        # * "assert name not in page"-style asserts fail for shared names with non-unique fields
        from model_bakery import baker

        baker.seed(cls.BAKER_SEED + 1)
        super()._pre_setup()


def initialize_baker_seed(baker_seed: int):
    SeedBakerMixin.BAKER_SEED = baker_seed
