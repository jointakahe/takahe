.PHONY: image docs compose_build compose_up compose_down

image:
	docker build -t takahe -f docker/Dockerfile .

docs:
	cd docs/ && make html

compose_build:
	docker-compose -f docker/docker-compose.yml build

compose_up:
	docker-compose -f docker/docker-compose.yml up

compose_down:
	docker-compose -f docker/docker-compose.yml down
