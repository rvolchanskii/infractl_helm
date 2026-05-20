#!/usr/bin/env python3
"""Simple wrapper around helm upgrade for generic-proxy chart."""

import argparse
import os

# import shlex
import subprocess
import sys
import tempfile
import yaml

from infractl_helm.lib import Balancer, BalancerError

KUBE_CONTEXT = 'k.yandex-team.ru'
HELM_BASE_CMD = ['helm', '--kube-context', KUBE_CONTEXT]


def load_templates_from_directory(base_dir='l7_upstream_templates'):
    """Load all templates from l7_upstream_templates/ directory recursively."""
    templates = {}
    # Use current working directory (same as other config files)
    templates_dir = os.path.join(os.getcwd(), base_dir)

    if not os.path.isdir(templates_dir):
        print(f'Templates directory not found: {templates_dir}', file=sys.stderr)
        sys.exit(1)

    # Recursively find all .yaml files
    for root, dirs, files in os.walk(templates_dir):
        for filename in sorted(files):  # sorted for deterministic order
            if filename.endswith('.yaml'):
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = yaml.safe_load(f)
                        if data:
                            for name, template in data.items():
                                if name in templates:
                                    print(f'Duplicate template name: {name}', file=sys.stderr)
                                    sys.exit(1)
                                templates[name] = template
                except Exception as e:
                    print(f'Error loading {filepath}: {e}', file=sys.stderr)
                    sys.exit(1)

    return templates


def create_templates_file():
    """Create temporary file with merged templates."""
    templates = load_templates_from_directory()
    merged = {'l7_upstream_templates': templates}

    # Create temp file in current working directory (same as other config files)
    fd, path = tempfile.mkstemp(suffix='.yaml', prefix='templates_', dir=os.getcwd())
    try:
        with os.fdopen(fd, 'w') as f:
            yaml.dump(merged, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        os.unlink(path)
        raise e
    return path


def run_cmd(cmd, *, capture_output=False, check=True):
    print('Running:', ' '.join(cmd))
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


def main():
    parser = argparse.ArgumentParser(
        description='Simple wrapper around helm upgrade for generic-proxy chart.',
        usage='%(prog)s --folder <path> [--diff] [--lint] [--template] [--unittest] [--upgrade] [--puncher] [--namespace <name> --balancer <name>] [extra helm args]',
        add_help=False,
    )
    parser.add_argument('--diff', action='store_true')
    parser.add_argument('--lint', action='store_true')
    parser.add_argument('--template', action='store_true')
    parser.add_argument('--unittest', action='store_true')
    parser.add_argument('--upgrade', action='store_true')
    parser.add_argument('--puncher', action='store_true')
    parser.add_argument('--namespace')
    parser.add_argument('--balancer')
    parser.add_argument('--folder', required=True, help='Path to a project forlder, which contains infractl namespaces')
    # Any arguments after the known ones should be passed directly to helm
    parser.add_argument('-h', '--help', action='help', help='show this help message and exit')

    args, extra = parser.parse_known_args()

    require_ns_balancer = args.diff or args.lint or args.template or args.upgrade or args.puncher
    if require_ns_balancer and (not args.namespace or not args.balancer):
        parser.print_usage(sys.stderr)
        sys.exit(1)

    helm_args = []
    templates_file = None
    if require_ns_balancer:
        # Create temporary merged templates file
        templates_file = create_templates_file()
        values_files = [
            'balancer_config.yaml',
            'components.yaml',
            templates_file,
            os.path.join(args.folder, args.namespace, f'{args.balancer}/values.yaml'),
        ]

        for v in values_files:
            if not os.path.isfile(v):
                print(f'Values file not found: {v}', file=sys.stderr)
                if templates_file and os.path.exists(templates_file):
                    os.unlink(templates_file)
                sys.exit(1)
            helm_args.extend(['-f', v])
            helm_args.extend(['-n', args.namespace])

    chart = os.path.join('helm', 'charts', 'generic-proxy')

    lint_cmd = HELM_BASE_CMD + ['lint', chart] + helm_args
    template_cmd = (
        HELM_BASE_CMD
        + ['template', args.balancer, chart, '--set', f'infractl_namespace={args.namespace}']
        + helm_args
        + extra
    )
    diff_cmd = (
        HELM_BASE_CMD
        + [
            'diff',
            'upgrade',
            args.balancer,
            chart,
            '--set',
            f'infractl_namespace={args.namespace}',
            '--detailed-exitcode',
        ]
        + helm_args
        + extra
    )
    unittest_cmd = HELM_BASE_CMD + ['unittest', chart]
    upgrade_cmd = (
        HELM_BASE_CMD
        + ['upgrade', args.balancer, chart, '--timeout', '600s', '--set', f'infractl_namespace={args.namespace}']
        + helm_args
        + extra
    )

    executed = False
    if args.lint or args.upgrade or args.puncher:
        run_cmd(lint_cmd)
        executed = True
    if args.unittest or args.upgrade:
        run_cmd(unittest_cmd)
        executed = True
    if args.template or args.upgrade:
        run_cmd(template_cmd)
        executed = True
    diff_result = None
    if args.diff or args.upgrade:
        diff_result = run_cmd(diff_cmd, capture_output=True, check=False)
        if diff_result.stdout:
            print(diff_result.stdout)
        if diff_result.stderr:
            print(diff_result.stderr, file=sys.stderr)
        if diff_result.returncode not in (0, 2):
            sys.exit(diff_result.returncode)
        executed = True
    if args.upgrade:
        if diff_result and diff_result.returncode == 0:
            print('No changes detected, skipping helm upgrade.')
        else:
            confirm = input('Changes detected. Proceed with helm upgrade? [y/N] ')
            if confirm.lower().startswith('y'):
                run_cmd(upgrade_cmd)
                executed = True
            else:
                print('Upgrade canceled.')
    if args.puncher:
        try:
            balancer = Balancer(args.namespace, args.balancer)
            balancer.request_puncher_rules()
            executed = True
        except BalancerError as exc:
            print(f'Puncher request failed: {exc}', file=sys.stderr)
            if templates_file and os.path.exists(templates_file):
                os.unlink(templates_file)
            sys.exit(1)

    if not executed:
        parser.print_usage(sys.stderr)
        if templates_file and os.path.exists(templates_file):
            os.unlink(templates_file)
        sys.exit(1)

    # Cleanup temporary templates file
    if templates_file and os.path.exists(templates_file):
        os.unlink(templates_file)


if __name__ == '__main__':
    main()
