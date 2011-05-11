import django_tables as tables


class CountryTable(tables.Table):
    name = tables.Column()
    population = tables.Column()
    tz = tables.Column(verbose_name='Time Zone')
    visits = tables.Column()


class ThemedCountryTable(CountryTable):
    class Meta:
        attrs = {'class': 'paleblue'}
