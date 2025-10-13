#!/usr/bin/env sh

./manage.py scss

VRT_CIBUILDID=$(git rev-parse --short HEAD) VRT_BRANCHNAME=$(git rev-parse --abbrev-ref HEAD) ./manage.py test  --tag selenium -k StaffSemesterViewRegressionTest