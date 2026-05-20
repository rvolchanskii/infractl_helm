# CI/CD
https://wiki.yandex-team.ru/taxi/backend/yangocloud/aws-taxi-rtc---arcadia-ci-dlja-helm-charta-infract/

### How to run it locally:
Lint
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --lint
```
Template
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --template
```
Template selected only
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --template -s templates/AwacsBalancer.yaml
```
Diff upgrade
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --diff
```
Upgrade(runs all previous steps)
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --upgrade
```
Request Puncher rules(obtain token from https://nda.ya.ru/t/RZ9vUAq_7KfRcy)
```properties
export PUNCHER_TOKEN="token"
```
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yandexcom.net --puncher
```
```properties
ya run -- --namespace aws-taxi-rtc-testing --balancer proxy-int.taxi.tst.yango.tech.yaml --puncher
```


When running with `--upgrade`, the script performs a `helm diff upgrade` first.
If no changes are detected, the upgrade step is skipped. If there are changes,
the script will ask for confirmation before applying `helm upgrade`.
