.. highlight:: shell

============
Contributing
============

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

Types of Contributions
----------------------

Report Bugs
~~~~~~~~~~~

Report bugs at https://github.com/bdraco/nexia/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

Fix Bugs
~~~~~~~~

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

Implement Features
~~~~~~~~~~~~~~~~~~

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

Write Documentation
~~~~~~~~~~~~~~~~~~~

Nexia could always use more documentation, whether as part of the
official Nexia docs, in docstrings, or even on the web in blog posts,
articles, and such.

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file an issue at https://github.com/bdraco/nexia/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

Get Started!
------------

Ready to contribute? Here's how to set up `nexia` for local development.

1. Fork the `nexia` repo on GitHub.
2. Clone your fork locally::

    $ git clone git@github.com:your_name_here/nexia.git

3. Install your local copy with `poetry <https://python-poetry.org/>`_. This
   creates a virtualenv and installs the runtime and development dependencies::

    $ cd nexia/
    $ poetry install

4. Create a branch for local development::

    $ git checkout -b name-of-your-bugfix-or-feature

   Now you can make your changes locally.

5. When you're done making changes, check that your changes pass the linters and
   the tests::

    $ poetry run ruff check nexia tests
    $ poetry run mypy nexia
    $ poetry run pytest

6. Commit your changes and push your branch to GitHub::

    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature

7. Submit a pull request through the GitHub website.

Pull Request Guidelines
-----------------------

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.rst.
3. The pull request should work for Python 3.5, 3.6, 3.7 and 3.8, and for PyPy. Check
   https://travis-ci.com/bdraco/nexia/pull_requests
   and make sure that the tests pass for all supported Python versions.

Tips
----

To run a subset of tests::

$ pytest tests.test_nexia


Deploying
---------

Releases are automated with python-semantic-release; there is nothing to run by hand.
On every merge to ``master`` the CI workflow inspects the Conventional Commit
messages, bumps the version, updates the changelog, tags the release, and
publishes to PyPI and GitHub Releases. Just make sure your PR title follows the
Conventional Commits format (``feat:``, ``fix:``, ``feat!:`` for a breaking
change, and so on), since the squashed PR title becomes the commit on ``master``.
