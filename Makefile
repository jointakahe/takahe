.PHONY: clean

image:
	docker build -t takahe -f docker/Dockerfile .
