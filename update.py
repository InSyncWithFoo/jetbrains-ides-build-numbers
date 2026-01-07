from __future__ import annotations

import json
import textwrap
from collections import defaultdict
from datetime import date  # noqa: TC003
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Self, final

import requests
from packaging.version import Version
from pandas import DataFrame
from pydantic import BaseModel

if TYPE_CHECKING:
	from collections.abc import Iterator


type RawVersion = str
type BuildNumber = str


class IDECode(StrEnum):
	CL = 'CLion'
	GO = 'GoLand'
	IIC = 'IntelliJ IDEA Community Edition'
	IIU = 'IntelliJ IDEA Ultimate'
	PCC = 'PyCharm Community Edition'
	PCP = 'PyCharm Professional Edition'
	PS = 'PhpStorm'
	RC = 'ReSharper C++'
	RD = 'Rider'
	RM = 'RubyMine'
	RR = 'RustRover'
	RS = 'ReSharper'
	WS = 'WebStorm'
	
	@classmethod
	def get(cls, member: str) -> Self | None:
		try:
			return cls[member]
		except KeyError:
			return None


@final
class Release(BaseModel):
	version: RawVersion
	build: BuildNumber | None
	date: date


class Product(BaseModel):
	code: str
	name: str
	releases: list[Release]


class IDEList(list[Product]):
	
	@property
	def releases(self) -> Iterator[tuple[IDECode, Release]]:
		yield from (
			(IDECode[ide.code], release)
			for ide in self
			for release in ide.releases
		)


def _retrieve_product_list() -> list[Product]:
	endpoint = 'https://data.services.jetbrains.com/products?release.type=release'
	one_minute = 60.0
	
	response = requests.get(endpoint, timeout = one_minute)
	
	return [Product(**element) for element in response.json()]


def _update_all_codes(products: list[Product]) -> None:
	path = Path(__file__).parent / 'all-product-codes.json'
	
	codes_and_names = [
		{'code': product.code, 'name': product.name}
		for product in products
	]
	codes_and_names.sort(key = lambda product: product['code'])
	
	with path.open('w') as file:
		json.dump(codes_and_names, file, indent = 4)


def _map_version_to_build_numbers(ides: IDEList) -> dict[RawVersion, dict[IDECode, BuildNumber | None]]:
	table: dict[RawVersion, dict[IDECode, BuildNumber | None]] = {}
	
	for code, release in ides.releases:
		version, build = release.version, release.build
		
		if build is None:
			continue
		
		if version not in table:
			table[version] = {}
		
		table[version][code] = build
	
	sorted_items = sorted(table.items(), reverse = True, key = lambda item: Version(item[0]))
	
	return dict(sorted_items)


def _construct_ide_table(ides: IDEList) -> DataFrame:
	columns = ['Version', *IDECode.__members__]
	table = DataFrame({column: [] for column in columns})
	
	version_to_build_numbers = _map_version_to_build_numbers(ides)
	
	for index, (version, codes_to_build_numbers) in enumerate(version_to_build_numbers.items()):
		build_numbers = [codes_to_build_numbers.get(code) for code in IDECode.__members__.values()]
		
		table.loc[index] = [version, *build_numbers]
	
	return table


def _table_notes() -> str:
	items: list[str] = []
	
	for code, member in IDECode.__members__.items():
		name = member.value
		item = f'<b>{code}</b>: {name}'
		
		items.append('&nbsp;'.join(item.split()))
	
	return ' | '.join(items)


def _update_table(ides: IDEList) -> None:
	table = _construct_ide_table(ides).to_markdown(index = False, stralign = 'left')
	
	new_content = textwrap.dedent('''
		# Build numbers

		{notes}

		{table}
	''')
	
	path = Path(__file__).parent / 'build-numbers.md'
	
	with path.open('w') as file:
		file.write(new_content.format(table = table, notes = _table_notes()).lstrip())


def _update_json(ides: IDEList) -> None:
	path = Path(__file__).parent / 'builds.json'
	code_to_releases: dict[IDECode, list[Release]] = defaultdict(list)
	
	for code, release in ides.releases:
		release_as_json = release.model_dump_json()
		code_to_releases[code.name].append(json.loads(release_as_json))
	
	with path.open('w') as file:
		json.dump(code_to_releases, file, separators = (',', ':'))


def main() -> None:
	products = _retrieve_product_list()
	ides = IDEList([
		product for product in products
		if IDECode.get(product.code) is not None
	])
	
	_update_all_codes(products)
	_update_table(ides)
	_update_json(ides)


if __name__ == '__main__':
	main()
