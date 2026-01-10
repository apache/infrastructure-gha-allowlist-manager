# GitHub Actions alowed patterns list

[approved_patterns.yml](https://github.com/apache/infrastructure-actions/tree/main/approved_patterns.yml) is a list of all of the allowed GitHub actions in our org.

see documentation [here](https://docs.github.com/en/rest/actions/permissions?apiVersion=2022-11-28#get-allowed-actions-and-reusable-workflows-for-an-organization) for token details.

This pipservice is intended to manage the list of allowed GitHub Actions within the Apache GitHub org

## Configuration
This service requires a config.yml 

```
verbosity: 5
logfile: stdout
gha_token: <TOKEN>
```

For verbosity values (0-5) please see the
[verbosity table](https://github.com/apache/infrastructure-gha-allowlist-manager/blob/main/gha-allowlist-manager.py#L28-L33)
