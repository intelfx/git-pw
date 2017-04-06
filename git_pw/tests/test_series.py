import unittest

from click.testing import CliRunner as CLIRunner
import mock

from git_pw import series


@mock.patch('git_pw.api.detail')
@mock.patch('git_pw.api.download')
@mock.patch('git_pw.utils.git_am')
class ApplyTestCase(unittest.TestCase):

    def test_apply_without_args(self, mock_git_am, mock_download, mock_detail):
        """Validate calling with no arguments."""

        rsp = {'mbox': 'http://example.com/api/patches/123/mbox/'}
        mock_detail.return_value = rsp
        mock_download.return_value = 'test.patch'

        runner = CLIRunner()
        result = runner.invoke(series.apply_cmd, ['123'])

        assert result.exit_code == 0, result
        mock_detail.assert_called_once_with('series', 123)
        mock_download.assert_called_once_with(rsp['mbox'])
        mock_git_am.assert_called_once_with(mock_download.return_value, ())

    def test_apply_with_args(self, mock_git_am, mock_download, mock_detail):
        """Validate passthrough of arbitrary arguments to git-am."""

        rsp = {'mbox': 'http://example.com/api/patches/123/mbox/'}
        mock_detail.return_value = rsp
        mock_download.return_value = 'test.patch'

        runner = CLIRunner()
        result = runner.invoke(series.apply_cmd, ['123', '--', '-3'])

        assert result.exit_code == 0, result
        mock_detail.assert_called_once_with('series', 123)
        mock_download.assert_called_once_with(rsp['mbox'])
        mock_git_am.assert_called_once_with(mock_download.return_value,
                                            ('-3',))


@mock.patch('git_pw.api.detail')
@mock.patch('git_pw.api.download')
@mock.patch('git_pw.api.get')
class DownloadTestCase(unittest.TestCase):

    def test_download(self, mock_get, mock_download, mock_detail):
        """Validate standard behavior."""

        rsp = {'mbox': 'http://example.com/api/patches/123/mbox/'}
        mock_detail.return_value = rsp
        mock_download.return_value = 'test.patch'

        runner = CLIRunner()
        result = runner.invoke(series.download_cmd, ['123'])

        assert result.exit_code == 0, result
        mock_detail.assert_called_once_with('series', 123)
        mock_download.assert_called_once_with(rsp['mbox'])
        mock_get.assert_not_called()

    def test_download_to_file(self, mock_get, mock_download, mock_detail):
        """Validate downloading to a file."""

        class MockResponse(object):
            @property
            def text(self):
                return b'alpha-beta'

        rsp = {'mbox': 'http://example.com/api/patches/123/mbox/'}
        mock_detail.return_value = rsp
        mock_get.return_value = MockResponse()

        runner = CLIRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(series.download_cmd, ['123', 'test.patch'])

            assert result.exit_code == 0, result

            with open('test.patch') as output:
                assert ['alpha-beta'] == output.readlines()

        mock_detail.assert_called_once_with('series', 123)
        mock_get.assert_called_once_with(rsp['mbox'])
        mock_download.assert_not_called()


class ShowTestCase(unittest.TestCase):

    @staticmethod
    def _get_series(**kwargs):
        rsp = {
            'id': 123,
            'date': '2017-01-01 00:00:00',
            'name': 'Sample series',
            'submitter': {
                'name': 'foo',
                'email': 'foo@bar.com',
            },
            'project': {
                'name': 'bar',
            },
            'version': '1',
            'total': 2,
            'received_total': 2,
            'received_all': True,
            'cover_letter': None,
            'patches': [],
        }

        rsp.update(**kwargs)

        return rsp

    @mock.patch('git_pw.api.detail')
    def test_show(self, mock_detail):
        """Validate standard behavior."""

        rsp = self._get_series()
        mock_detail.return_value = rsp

        runner = CLIRunner()
        result = runner.invoke(series.show_cmd, ['123'])

        assert result.exit_code == 0, result
        mock_detail.assert_called_once_with('series', 123)


@mock.patch('git_pw.utils.echo_via_pager', new=mock.Mock)
@mock.patch('git_pw.api.version', return_value=(1, 0))
@mock.patch('git_pw.api.index')
class ListTestCase(unittest.TestCase):

    @staticmethod
    def _get_series(**kwargs):
        return ShowTestCase._get_series(**kwargs)

    @staticmethod
    def _get_people(**kwargs):
        rsp = {
            'id': 1,
            'name': 'John Doe',
            'email': 'john@example.com',
        }
        rsp.update(**kwargs)
        return rsp

    def test_list(self, mock_index, mock_version):
        """Validate standard behavior."""

        rsp = [self._get_series()]
        mock_index.return_value = rsp

        runner = CLIRunner()
        result = runner.invoke(series.list_cmd, [])

        assert result.exit_code == 0, result
        mock_index.assert_called_once_with('series', [
            ('q', None), ('page', None), ('per_page', None),
            ('order', '-date')])

    def test_list_with_filters(self, mock_index, mock_version):
        """Validate behavior with filters applied.

        Apply all filters, including those for pagination.
        """

        people_rsp = [self._get_people()]
        series_rsp = [self._get_series()]
        mock_index.side_effect = [people_rsp, series_rsp]

        runner = CLIRunner()
        result = runner.invoke(series.list_cmd, [
            '--submitter', 'john@example.com', '--limit', 1, '--page', 1,
            '--sort', '-name', 'test'])

        assert result.exit_code == 0, result
        calls = [
            mock.call('people', [('q', 'john@example.com')]),
            mock.call('series', [
                ('submitter', 1), ('q', 'test'), ('page', 1), ('per_page', 1),
                ('order', '-name')])]

        mock_index.assert_has_calls(calls)

    @mock.patch('git_pw.series.LOG')
    def test_list_with_invalid_filters(self, mock_log, mock_index,
                                       mock_version):
        """Validate behavior with filters applied.

        Try to filter against a sumbmitter filter that's too broad. This should
        error out saying that too many possible submitters were found.
        """

        people_rsp = [self._get_people(), self._get_people()]
        series_rsp = [self._get_series()]
        mock_index.side_effect = [people_rsp, series_rsp]

        runner = CLIRunner()
        result = runner.invoke(series.list_cmd, ['--submitter',
                                                 'john@example.com'])

        assert result.exit_code == 1, result
        assert mock_log.error.called