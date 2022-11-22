.PHONY: clean

image:
	docker build -t takahe -f docker/Dockerfile .

docs:
	cd docs/ && make html

compose_up:
	docker-compose -f docker/docker-compose.yml up
