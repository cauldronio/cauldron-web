# Cauldron

New Cauldron that makes use of grimoirelab tools for analyzing GitHub users, organizations and git repositories.

If you want to try it out, refer to the [deployment repository](https://gitlab.com/cauldron2/cauldron-deployment).

## Developing live-version

Maybe you could want to modify a live-version of Cauldron to see changes in real time. To make this possible, you will need to make some adjustments in your configuration:

- First, you will need to clone this repository into your local machine:

  ```bash
  $ git clone https://gitlab.com/cauldron2/cauldron-web.git
  ```

- Next, you will need to modify the file `<deployment_path>/playbooks/roles/run_cauldron/tasks/run_django.yml` from the [deployment repository](https://gitlab.com/cauldron2/cauldron-deployment), adding the next line at the end of the `volumes` section:

  ```bash
  - "<cauldron_path>:/code/cauldron"
  ```

- The next time you run Cauldron, every change made to your local version of this repository will overwrite the one located in the container of the deployment repository.
